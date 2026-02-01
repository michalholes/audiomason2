#!/usr/bin/env python3
"""audit/summarize_audit.py

Audit summarizer: compares the latest two audit result YAML files for a given
profile and produces:

1) A machine-readable delta report YAML (audit/results/audit_summary_*.yaml)
2) A long, human-readable Markdown report (audit/summary.md, overwritten)
3) A SHORT CLI report on stdout (intended for frequent runs)

This tool does NOT run tests or runtime commands. It only reads existing audit
result files produced by audit/evaluate_audit.py.

By default, git auto publish is ON: it commits+pushes ONLY the files written by
the summarizer (delta YAML + audit/summary.md). Disable with --no-git.

Usage (repo root):
  python3 audit/summarize_audit.py --profile C3_ALL_v5
  python3 audit/summarize_audit.py --profile C3_ALL_v5 --no-git
  python3 audit/summarize_audit.py --profile C3_ALL_v5 --git-no-push
"""

from __future__ import annotations

import argparse
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

STATUS_ORDER: dict[str, int] = {
    "PASS": 0,
    "PARTIAL": 1,
    "DEBT": 2,
    "UNKNOWN": 3,
}


@dataclass(frozen=True)
class AuditDoc:
    path: Path
    profile: str
    timestamp: str
    fingerprint: str
    verdict: str
    technical_results: list[dict[str, Any]]
    cert_reasons: list[str]
    cert_errors: list[str]


def _safe_relpath(repo: Path, p: Path) -> str:
    try:
        return str(p.relative_to(repo))
    except Exception:
        return str(p)


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid YAML root in {path}")
    return data


def _get_str(d: dict[str, Any], key: str, default: str = "") -> str:
    v = d.get(key, default)
    return v if isinstance(v, str) else default


def _parse_audit_doc(path: Path) -> AuditDoc | None:
    if not path.name.endswith(".yaml"):
        return None
    if path.name.startswith("runtime_evidence"):
        return None
    if not path.name.startswith("audit_"):
        return None
    if path.name.startswith("audit_summary_"):
        return None
    if "_summary_" in path.name:
        return None

    d = _read_yaml(path)

    schema = d.get("audit_result_schema")
    if not isinstance(schema, int) or schema != 1:
        return None

    profile = _get_str(d, "profile", "")
    if not profile:
        return None

    meta = d.get("meta", {})
    if not isinstance(meta, dict):
        meta = {}
    timestamp = _get_str(meta, "timestamp", "unknown_ts")
    fingerprint = _get_str(meta, "inputs_fingerprint", "unknown_fp")

    cert = d.get("certification", {})
    if not isinstance(cert, dict):
        cert = {}
    verdict = _get_str(cert, "verdict", "UNKNOWN")

    tech_results = d.get("technical_results", [])
    if not isinstance(tech_results, list):
        tech_results = []

    cert_reasons = cert.get("reasons", [])
    if not isinstance(cert_reasons, list):
        cert_reasons = []
    cert_reasons_s = [str(x) for x in cert_reasons if isinstance(x, (str, int, float))]

    cert_errors = cert.get("errors", [])
    if not isinstance(cert_errors, list):
        cert_errors = []
    cert_errors_s = [str(x) for x in cert_errors if isinstance(x, (str, int, float))]

    return AuditDoc(
        path=path,
        profile=profile,
        timestamp=timestamp,
        fingerprint=fingerprint,
        verdict=verdict,
        technical_results=[x for x in tech_results if isinstance(x, dict)],
        cert_reasons=cert_reasons_s,
        cert_errors=cert_errors_s,
    )


def _iter_audit_docs(results_dir: Path, profile: str) -> list[AuditDoc]:
    docs: list[AuditDoc] = []
    for p in sorted(results_dir.glob("audit_*.yaml"), key=lambda x: x.name):
        doc = _parse_audit_doc(p)
        if doc and doc.profile == profile:
            docs.append(doc)
    return docs


def _get_result(r: dict[str, Any]) -> str:
    v = r.get("result")
    if isinstance(v, str) and v:
        return v
    v2 = r.get("status")
    if isinstance(v2, str) and v2:
        return v2
    return "UNKNOWN"


def _status_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"PASS": 0, "PARTIAL": 0, "DEBT": 0, "UNKNOWN": 0}
    for r in results:
        s = _get_result(r)
        if isinstance(s, str) and s in counts:
            counts[s] += 1
    return counts


def _index_by_req(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in results:
        rid = r.get("requirement_id")
        if isinstance(rid, str) and rid:
            out[rid] = r
    return out


def _delta_counts(cur: dict[str, int], prev: dict[str, int] | None) -> dict[str, int]:
    if prev is None:
        return {k: cur.get(k, 0) for k in ("PASS", "PARTIAL", "DEBT", "UNKNOWN")}
    return {k: cur.get(k, 0) - prev.get(k, 0) for k in ("PASS", "PARTIAL", "DEBT", "UNKNOWN")}


def _compare_status(a: str, b: str) -> int:
    return STATUS_ORDER.get(a, 99) - STATUS_ORDER.get(b, 99)


def _build_delta(current: AuditDoc, previous: AuditDoc | None) -> dict[str, Any]:
    cur_counts = _status_counts(current.technical_results)
    prev_counts = _status_counts(previous.technical_results) if previous else None

    cur_index = _index_by_req(current.technical_results)
    prev_index = _index_by_req(previous.technical_results) if previous else {}

    improvements: list[dict[str, Any]] = []
    regressions: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    unknowns: list[dict[str, Any]] = []

    all_req_ids = sorted(set(cur_index.keys()) | set(prev_index.keys()))
    for rid in all_req_ids:
        cur = cur_index.get(rid)
        prev = prev_index.get(rid)

        cur_status_s = _get_result(cur) if isinstance(cur, dict) else "UNKNOWN"
        prev_status_s = _get_result(prev) if isinstance(prev, dict) else "UNKNOWN"

        if previous is not None and cur_status_s != prev_status_s:
            diff = _compare_status(cur_status_s, prev_status_s)
            item = {"requirement_id": rid, "from": prev_status_s, "to": cur_status_s}
            if diff < 0:
                improvements.append(item)
            elif diff > 0:
                regressions.append(item)

        if cur_status_s in ("DEBT", "PARTIAL", "UNKNOWN"):
            reason = ""
            if isinstance(cur, dict):
                reason_v = cur.get("reason")
                reason = reason_v if isinstance(reason_v, str) else ""
            if cur_status_s == "UNKNOWN":
                unknowns.append({"requirement_id": rid, "reason": reason})
            else:
                blockers.append({"requirement_id": rid, "status": cur_status_s, "reason": reason})

    unknown_reason_counts: dict[str, int] = {}
    unknown_samples: dict[str, list[str]] = {}
    per_domain_counts: dict[str, dict[str, int]] = {}
    for r in current.technical_results:
        if not isinstance(r, dict):
            continue
        rid_v = r.get("requirement_id")
        dom_v = r.get("domain")
        rid_s = rid_v if isinstance(rid_v, str) else ""
        dom_s = dom_v if isinstance(dom_v, str) and dom_v else "UNKNOWN_DOMAIN"
        res_s = _get_result(r)
        per = per_domain_counts.setdefault(
            dom_s, {"PASS": 0, "PARTIAL": 0, "DEBT": 0, "UNKNOWN": 0}
        )
        if res_s in per:
            per[res_s] += 1
        if res_s == "UNKNOWN":
            reason_v = r.get("reason")
            reason = reason_v if isinstance(reason_v, str) else "UNKNOWN_REASON"
            unknown_reason_counts[reason] = unknown_reason_counts.get(reason, 0) + 1
            lst = unknown_samples.setdefault(reason, [])
            if rid_s and len(lst) < 16 and rid_s not in lst:
                lst.append(rid_s)

    def _unknown_action(reason: str) -> str:
        if reason == "NO_EVIDENCE":
            return (
                "Add/enable evidence: map pytest tests or produce runtime evidence "
                "for requirements."
            )
        if reason == "RUBRIC_INVALID":
            return "Fix audit_rubric.yaml structure/fields for this requirement."
        return "Inspect requirement details in the audit YAML (reason/evidence)."

    diagnosis_block = {
        "verdict_reasons": list(current.cert_reasons),
        "verdict_errors": list(current.cert_errors),
        "unknown_reasons": [
            {
                "reason": k,
                "count": unknown_reason_counts[k],
                "action": _unknown_action(k),
                "sample_requirement_ids": list(unknown_samples.get(k, [])),
            }
            for k in sorted(unknown_reason_counts.keys())
        ],
        "per_domain_counts": {k: per_domain_counts[k] for k in sorted(per_domain_counts.keys())},
    }

    improvements.sort(key=lambda x: x["requirement_id"])
    regressions.sort(key=lambda x: x["requirement_id"])
    blockers.sort(key=lambda x: (x.get("status", ""), x["requirement_id"]))
    unknowns.sort(key=lambda x: x["requirement_id"])

    return {
        "audit_summary_schema": 1,
        "profile": current.profile,
        "meta": {
            "current": {
                "path": str(current.path),
                "timestamp": current.timestamp,
                "inputs_fingerprint": current.fingerprint,
                "verdict": current.verdict,
            },
            "previous": (
                {
                    "path": str(previous.path),
                    "timestamp": previous.timestamp,
                    "inputs_fingerprint": previous.fingerprint,
                    "verdict": previous.verdict,
                }
                if previous
                else None
            ),
        },
        "summary": {
            "verdict": {
                "current": current.verdict,
                "previous": previous.verdict if previous else None,
                "changed": (previous.verdict != current.verdict) if previous else None,
            },
            "counts": {
                "current": cur_counts,
                "previous": prev_counts,
                "delta": _delta_counts(cur_counts, prev_counts),
            },
        },
        "improvements": improvements,
        "regressions": regressions,
        "blockers": blockers,
        "unknowns": unknowns,
        "diagnosis": diagnosis_block,
        "notes": [
            "This report compares audit/evaluate_audit.py outputs only.",
            "Blockers and unknowns are based on the CURRENT audit result.",
        ],
    }


def _allocate_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suf = path.suffix
    for i in range(1, 1000):
        cand = path.with_name(f"{stem}__{i}{suf}")
        if not cand.exists():
            return cand
    raise RuntimeError(f"unable to allocate unique output path: {path}")


def _build_default_output_path(
    results_dir: Path, profile: str, current: AuditDoc, previous: AuditDoc | None
) -> Path:
    safe_ts = re.sub(r"[^0-9A-Za-z_.:-]+", "_", current.timestamp or "unknown_ts")
    prev_fp = previous.fingerprint if previous else "none"
    return (
        results_dir / f"audit_summary_{profile}_{safe_ts}_{current.fingerprint}_vs_{prev_fp}.yaml"
    )


def _git_state_allows_publish(repo: Path) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode != 0 or r.stdout.strip() != "true":
            return False, "not a git work tree"
        b = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        branch = b.stdout.strip()
        if branch == "HEAD" or not branch:
            return False, "detached HEAD"
        dotgit = repo / ".git"
        if (dotgit / "MERGE_HEAD").exists():
            return False, "merge in progress"
        if (dotgit / "CHERRY_PICK_HEAD").exists():
            return False, "cherry-pick in progress"
        if (dotgit / "rebase-apply").exists() or (dotgit / "rebase-merge").exists():
            return False, "rebase in progress"
        return True, ""
    except Exception as e:
        return False, f"git state check failed: {e}"


def _git_publish_files(
    repo: Path,
    files: list[Path],
    message: str,
    remote: str,
    branch: str | None,
    push: bool,
    no_verify: bool,
) -> tuple[str, str]:
    ok, reason = _git_state_allows_publish(repo)
    if not ok:
        return "skipped", reason

    if branch is None:
        b = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        branch = b.stdout.strip() or None
    if branch is None:
        return "skipped", "unable to determine branch"

    rel_files = [_safe_relpath(repo, p) for p in files]

    add = subprocess.run(
        ["git", "add", "--", *rel_files],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if add.returncode != 0:
        msg = ((add.stderr or "") + "\n" + (add.stdout or "")).strip()
        return "error", f"git add failed: {msg}"

    cmd = ["git", "commit", "--only", "-m", message]
    if no_verify:
        cmd.append("--no-verify")
    cmd.extend(["--", *rel_files])
    c = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, check=False)
    if c.returncode != 0:
        msg = ((c.stderr or "") + "\n" + (c.stdout or "")).strip()
        low = msg.lower()
        if "nothing to commit" in low or "no changes" in low:
            sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
            return "ok", f"commit={sha} push=skipped(nothing-to-commit)"
        return "error", f"git commit failed: {msg}"

    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()

    if not push:
        return "ok", f"commit={sha} push=skipped"

    p2 = subprocess.run(
        ["git", "push", remote, branch],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if p2.returncode != 0:
        msg = ((p2.stderr or "") + "\n" + (p2.stdout or "")).strip()
        return "error", f"commit={sha} push=failed: {msg}"
    return "ok", f"commit={sha} push=ok"


def summarize_latest(results_dir: Path, profile: str) -> tuple[Path, dict[str, Any]]:
    docs = _iter_audit_docs(results_dir, profile)
    if not docs:
        raise FileNotFoundError(
            f"no audit result files found for profile={profile} in {results_dir} (schema=1)"
        )

    def sort_key(d: AuditDoc) -> tuple[str, str]:
        return (d.timestamp or "unknown_ts", d.path.name)

    docs_sorted = sorted(docs, key=sort_key)
    current = docs_sorted[-1]
    previous = docs_sorted[-2] if len(docs_sorted) >= 2 else None

    report = _build_delta(current, previous)
    out_path = _allocate_unique_path(
        _build_default_output_path(results_dir, profile, current, previous)
    )
    out_path.write_text(
        yaml.safe_dump(report, sort_keys=True, allow_unicode=False),
        encoding="utf-8",
    )
    return out_path, report


def _fmt_delta_int(x: int) -> str:
    return f"+{x}" if x > 0 else str(x)


def _render_short(report: dict[str, Any]) -> str:
    summ = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    counts = summ.get("counts", {}) if isinstance(summ.get("counts"), dict) else {}
    cur_counts = counts.get("current", {}) if isinstance(counts.get("current"), dict) else {}
    delta = counts.get("delta", {}) if isinstance(counts.get("delta"), dict) else {}

    imps = report.get("improvements", [])
    regs = report.get("regressions", [])

    lines: list[str] = []
    lines.append("----------------")
    lines.append("IMPROVEMENTS:")
    if not isinstance(imps, list) or not imps:
        lines.append("  (none)")
    else:
        for it in imps[:25]:
            if isinstance(it, dict) and isinstance(it.get("requirement_id"), str):
                rid = it["requirement_id"]
                fr = it.get("from")
                to = it.get("to")
                if isinstance(fr, str) and isinstance(to, str):
                    lines.append(f"  - {rid}  {fr} -> {to}")
                else:
                    lines.append(f"  - {rid}")
        if len(imps) > 25:
            lines.append(f"  ... and {len(imps) - 25} more")
    lines.append("REGRESSIONS:")
    if not isinstance(regs, list) or not regs:
        lines.append("  (none)")
    else:
        for it in regs[:25]:
            if isinstance(it, dict) and isinstance(it.get("requirement_id"), str):
                rid = it["requirement_id"]
                fr = it.get("from")
                to = it.get("to")
                if isinstance(fr, str) and isinstance(to, str):
                    lines.append(f"  - {rid}  {fr} -> {to}")
                else:
                    lines.append(f"  - {rid}")
        if len(regs) > 25:
            lines.append(f"  ... and {len(regs) - 25} more")

    lines.append("----------------")
    for k in ("PASS", "PARTIAL", "DEBT", "UNKNOWN"):
        cv = int(cur_counts.get(k, 0)) if isinstance(cur_counts.get(k, 0), int) else 0
        dv = int(delta.get(k, 0)) if isinstance(delta.get(k, 0), int) else 0
        lines.append(f"  {k:7s} {cv:4d}  ({_fmt_delta_int(dv)})")
    lines.append("----------------")

    diag = report.get("diagnosis", {}) if isinstance(report.get("diagnosis"), dict) else {}
    unkrs = diag.get("unknown_reasons", [])
    next_line = "Inspect requirement details in the audit YAML (reason/evidence)."
    examples: list[str] = []
    if isinstance(unkrs, list) and unkrs:
        # Pick the most important reason deterministically: highest count, then reason name.
        items: list[dict[str, Any]] = [x for x in unkrs if isinstance(x, dict)]
        if items:
            items.sort(
                key=lambda x: (
                    -int(x.get("count", 0)) if isinstance(x.get("count", 0), int) else 0,
                    str(x.get("reason", "")),
                )
            )
            top = items[0]
            action = top.get("action")
            if isinstance(action, str) and action.strip():
                next_line = action.strip()
            samples = top.get("sample_requirement_ids")
            if isinstance(samples, list):
                examples = [str(s) for s in samples[:8]]

    lines.append(f"      next: {next_line}")
    if examples:
        lines.append(f"      examples: {', '.join(examples)}")
    else:
        lines.append("      examples: (none)")
    return "\n".join(lines)


def _render_long_markdown(report: dict[str, Any]) -> str:
    prof = report.get("profile", "")
    meta = report.get("meta", {}) if isinstance(report.get("meta"), dict) else {}
    cur = meta.get("current", {}) if isinstance(meta.get("current"), dict) else {}
    prev = meta.get("previous")
    summ = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    verdict = summ.get("verdict", {}) if isinstance(summ.get("verdict"), dict) else {}
    counts = summ.get("counts", {}) if isinstance(summ.get("counts"), dict) else {}
    cur_counts = counts.get("current", {}) if isinstance(counts.get("current"), dict) else {}
    delta = counts.get("delta", {}) if isinstance(counts.get("delta"), dict) else {}

    imps = report.get("improvements", [])
    regs = report.get("regressions", [])
    blks = report.get("blockers", [])
    unks = report.get("unknowns", [])
    diag = report.get("diagnosis", {}) if isinstance(report.get("diagnosis"), dict) else {}
    unkrs = diag.get("unknown_reasons", [])
    pdc = diag.get("per_domain_counts", {})

    def fmt_list(items: Any, limit: int = 200) -> str:
        if not isinstance(items, list) or not items:
            return "- (none)\n"
        out_lines: list[str] = []
        for it in items[:limit]:
            if not isinstance(it, dict):
                continue
            rid = it.get("requirement_id")
            if not isinstance(rid, str) or not rid:
                continue
            line = f"- {rid}"
            if "from" in it and "to" in it:
                fr = it.get("from")
                to = it.get("to")
                if isinstance(fr, str) and isinstance(to, str):
                    line += f" ({fr} -> {to})"
            if "status" in it:
                st = it.get("status")
                if isinstance(st, str) and st:
                    line += f" [{st}]"
            rs = it.get("reason")
            if isinstance(rs, str) and rs:
                line += f" - {rs}"
            out_lines.append(line)
        if len(items) > limit:
            out_lines.append(f"- ... and {len(items) - limit} more")
        return "\n".join(out_lines) + "\n"

    md: list[str] = []
    md.append(f"# Audit Summary ({prof})")
    md.append("")
    md.append(f"Current: {cur.get('timestamp')}  verdict={verdict.get('current')}")
    if isinstance(prev, dict):
        md.append(f"Previous: {prev.get('timestamp')}  verdict={verdict.get('previous')}")
    else:
        md.append("Previous: none")
    md.append("")
    md.append("## Counts (current / delta)")
    for k in ("PASS", "PARTIAL", "DEBT", "UNKNOWN"):
        cv = int(cur_counts.get(k, 0)) if isinstance(cur_counts.get(k, 0), int) else 0
        dv = int(delta.get(k, 0)) if isinstance(delta.get(k, 0), int) else 0
        md.append(f"- {k}: {cv} ({_fmt_delta_int(dv)})")
    md.append("")
    md.append("## Improvements")
    md.append(fmt_list(imps))
    md.append("## Regressions")
    md.append(fmt_list(regs))
    md.append("## Blockers (current)")
    md.append(fmt_list(blks))
    md.append("## Unknowns (current)")
    md.append(fmt_list(unks))
    md.append("## Unknown diagnosis")
    if not isinstance(unkrs, list) or not unkrs:
        md.append("- (none)\n")
    else:
        for item in unkrs[:50]:
            if not isinstance(item, dict):
                continue
            reason = item.get("reason")
            count = item.get("count")
            action = item.get("action")
            samples = item.get("sample_requirement_ids")
            reason_s = reason if isinstance(reason, str) else "UNKNOWN_REASON"
            count_i = int(count) if isinstance(count, int) else 0
            action_s = action if isinstance(action, str) else ""
            md.append(f"- {reason_s}: {count_i}")
            if action_s:
                md.append(f"  - next: {action_s}")
            if isinstance(samples, list) and samples:
                ex = ", ".join([str(x) for x in samples[:16]])
                md.append(f"  - examples: {ex}")
        md.append("")
    md.append("## Domains (current)")
    if not isinstance(pdc, dict) or not pdc:
        md.append("- (none)\n")
    else:
        for dom in sorted(pdc.keys()):
            c = pdc.get(dom)
            if not isinstance(c, dict):
                continue
            p_ = int(c.get("PASS", 0)) if isinstance(c.get("PASS", 0), int) else 0
            pa_ = int(c.get("PARTIAL", 0)) if isinstance(c.get("PARTIAL", 0), int) else 0
            d_ = int(c.get("DEBT", 0)) if isinstance(c.get("DEBT", 0), int) else 0
            u_ = int(c.get("UNKNOWN", 0)) if isinstance(c.get("UNKNOWN", 0), int) else 0
            if (p_ + pa_ + d_ + u_) == 0:
                continue
            md.append(f"- {dom}: PASS={p_} PARTIAL={pa_} DEBT={d_} UNKNOWN={u_}")
    md.append("")
    md.append(
        "(This file is generated by audit/summarize_audit.py and is overwritten on each run.)"
    )
    md.append("")

    return "\n".join(md)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Summarize audit results (delta report).")

    ap.add_argument("--profile", required=True, help="Certification profile name, e.g. C3_ALL_v5")
    ap.add_argument(
        "--results-dir", default="audit/results", help="Results directory (default: audit/results)"
    )
    ap.add_argument("--no-git", action="store_true", help="Disable git commit/push for outputs.")
    ap.add_argument("--git-no-push", action="store_true", help="Commit but do not push.")
    ap.add_argument("--git-remote", default="origin", help="Git remote for push (default: origin)")
    ap.add_argument("--git-branch", default=None, help="Branch to push (default: current branch)")
    ap.add_argument("--git-no-verify", action="store_true", help="Pass --no-verify to git commit.")
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress stdout output (errors still print).",
    )
    ap.add_argument(
        "--print-files",
        action="store_true",
        help="Print output file paths (useful with --verbose in audit_report.py).",
    )

    ns = ap.parse_args(argv)

    repo = Path(".").resolve()
    results_dir = (repo / ns.results_dir).resolve()

    try:
        out_path, report = summarize_latest(results_dir=results_dir, profile=ns.profile)

        # Always write long human report (overwritten).
        md_path = (repo / "audit" / "summary.md").resolve()
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_render_long_markdown(report), encoding="utf-8")

        if not ns.no_git:
            msg = f"audit: summarize {ns.profile} @ {report['meta']['current']['timestamp']}"
            status, detail = _git_publish_files(
                repo=repo,
                files=[out_path, md_path],
                message=msg,
                remote=str(ns.git_remote),
                branch=ns.git_branch,
                push=(not ns.git_no_push),
                no_verify=bool(ns.git_no_verify),
            )
            if status == "error":
                raise RuntimeError(detail)

        if not ns.quiet:
            if ns.print_files:
                print(f"ok: wrote {out_path}")
                print(f"ok: wrote {md_path}")
            print(_render_short(report))

        return 0
    except Exception as e:
        print(f"error: {e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
