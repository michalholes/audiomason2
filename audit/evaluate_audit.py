#!/usr/bin/env python3
"""audit/evaluate_audit.py

Audit evaluator: converts raw evidence artifacts into a single audit result and a
certification verdict.

Design goals:
- Deterministic: same inputs -> same output.
- Non-executing for evidence: it does NOT run pytest or runtime commands.
- No guessing: missing or invalid evidence yields UNKNOWN
  (and certification FAIL if profile requires it).

Inputs:
- audit/audit_rubric.yaml (required)
- audit/results/pytest_junit.xml (optional)
- audit/results/runtime_evidence*.yaml (optional, can be multiple)

Output:
- A new YAML file written into audit/results/ (never overwrites existing files).

By default, the evaluator will also commit+push the generated audit result file using a
targeted git workflow that stages/commits ONLY the file(s) created by the evaluator.
This default behavior can be disabled with --no-git.

Usage (repo root):
  python3 audit/evaluate_audit.py --profile C3_ALL_v5

Typical:
  python3 audit/evaluate_audit.py --profile C3_ALL_v5
  python3 audit/evaluate_audit.py --profile C3_ALL_v5 --no-git
  python3 audit/evaluate_audit.py --profile C3_ALL_v5 --git-no-push
  python3 audit/evaluate_audit.py --profile C3_ALL_v5 --future-domain-policy v1
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

RESULT_ENUM = ("PASS", "PARTIAL", "DEBT", "UNKNOWN")
FUTURE_DOMAIN_POLICIES = ("v1", "informational")
AUDIT_RESULT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EvidencePointer:
    kind: str
    text: str
    keys: dict[str, Any]


@dataclass(frozen=True)
class RequirementResult:
    requirement_id: str
    domain: str
    result: str
    reason: str
    evidence: list[EvidencePointer]


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _safe_relpath(repo: Path, path: Path) -> str:
    try:
        return str(path.relative_to(repo))
    except Exception:
        return path.as_posix()


def _parse_iso_dt(value: str) -> datetime | None:
    v = value.strip()
    if not v:
        return None
    try:
        if v.endswith("Z"):
            return datetime.fromisoformat(v[:-1])
        return datetime.fromisoformat(v)
    except Exception:
        return None


def _timestamp_key(value: str) -> tuple[int, str]:
    dt = _parse_iso_dt(value)
    if dt is None:
        return (-1, value)
    return (int(dt.timestamp()), value)


def _max_timestamp(values: Sequence[str]) -> str | None:
    cleaned = [v for v in (str(x).strip() for x in values) if v]
    if not cleaned:
        return None
    return max(cleaned, key=lambda s: _timestamp_key(s))


def _list_runtime_evidence_files(results_dir: Path) -> list[Path]:
    files = sorted(results_dir.glob("runtime_evidence*.yaml"))
    return [p for p in files if p.is_file()]


def _read_git_sha(repo: Path) -> str | None:
    # Prefer `git rev-parse` because it is robust to packed refs.
    try:
        p = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
        )
        if p.returncode == 0:
            sha = (p.stdout or "").strip()
            return sha or None
    except Exception:
        pass
    return None


def _stable_inputs_fingerprint(repo: Path, paths: Sequence[Path]) -> str:
    h = hashlib.sha256()
    for p in paths:
        rel = _safe_relpath(repo, p)
        h.update(rel.encode("utf-8"))
        if p.exists() and p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()[:12]


def _parse_pytest_junit(junit_path: Path) -> dict[str, Any]:
    tree = ET.parse(junit_path)
    root = tree.getroot()

    suites: list[ET.Element] = []
    if root.tag == "testsuite":
        suites = [root]
    elif root.tag == "testsuites":
        suites = [c for c in root if c.tag == "testsuite"]
    else:
        suites = [root]

    suite_ts = None
    for s in suites:
        ts = s.attrib.get("timestamp")
        if ts:
            suite_ts = ts
            break

    cases: list[dict[str, Any]] = []
    for s in suites:
        for tc in s.iter("testcase"):
            classname = tc.attrib.get("classname", "")
            name = tc.attrib.get("name", "")
            file_ = tc.attrib.get("file", "")
            outcome = "pass"
            if list(tc.findall("failure")) or list(tc.findall("error")):
                outcome = "fail"
            elif list(tc.findall("skipped")):
                outcome = "skip"

            nodeid = ""
            if file_:
                nodeid = f"{file_}::{name}" if name else file_
            elif classname and name:
                nodeid = f"{classname}::{name}"
            else:
                nodeid = name or classname or "<unknown>"

            cases.append(
                {
                    "nodeid": nodeid,
                    "classname": classname,
                    "name": name,
                    "file": file_,
                    "outcome": outcome,
                }
            )
    return {"suite_timestamp": suite_ts, "cases": cases}


def _domain_for_testcase(tc: dict[str, Any], mapping: dict[str, Any]) -> str | None:
    name = str(tc.get("name", "") or "")
    classname = str(tc.get("classname", "") or "")
    file_ = str(tc.get("file", "") or "")
    hay = f"{name} {classname}".strip()

    by_prefix = mapping.get("matching", {}).get("by_test_name_prefix", {})
    for domain, prefixes in by_prefix.items():
        for pref in prefixes or []:
            if pref and (name.startswith(pref) or hay.startswith(pref)):
                return str(domain)

    by_path_contains = mapping.get("matching", {}).get("by_path_contains", {})
    for domain, needles in by_path_contains.items():
        for nd in needles or []:
            if nd and nd in file_:
                return str(domain)

    return None


def _domain_testcases(
    junit: dict[str, Any],
    mapping: dict[str, Any],
    domain: str,
) -> list[dict[str, Any]]:
    out = []
    for tc in junit.get("cases", []):
        if _domain_for_testcase(tc, mapping) == domain:
            out.append(tc)
    return out


def _domain_test_summary(
    junit: dict[str, Any],
    mapping: dict[str, Any],
    domain: str,
) -> dict[str, int]:
    totals = {"pass": 0, "fail": 0, "skip": 0, "total": 0}
    for tc in _domain_testcases(junit, mapping, domain):
        oc = tc.get("outcome", "pass")
        if oc not in ("pass", "fail", "skip"):
            oc = "pass"
        totals[oc] += 1
        totals["total"] += 1
    return totals


@dataclass(frozen=True)
class RuntimeRunRef:
    requirement_id: str
    evidence_file: str
    run_index: int
    run: dict[str, Any]


def _load_runtime_runs(
    files: list[Path],
) -> tuple[dict[str, RuntimeRunRef], dict[str, list[RuntimeRunRef]], list[str]]:
    # Policy: files sorted by name; for a given requirement_id, the latest seen run wins.
    # Deterministic: no time-based selection, only file order and run order.
    rid_latest: dict[str, RuntimeRunRef] = {}
    rid_all: dict[str, list[RuntimeRunRef]] = {}
    errors: list[str] = []

    for p in sorted(files, key=lambda x: x.name):
        data = _read_yaml(p)
        runs = data.get("runs", [])
        if runs is None:
            runs = []
        if not isinstance(runs, list):
            errors.append(f"runtime evidence invalid runs type in {p.name}")
            continue

        for idx, r in enumerate(runs):
            if not isinstance(r, dict):
                continue
            rid = str(r.get("requirement_id", "") or "").strip()
            if not rid:
                continue
            ref = RuntimeRunRef(
                requirement_id=rid,
                evidence_file=p.name,
                run_index=idx,
                run=r,
            )
            rid_latest[rid] = ref
            rid_all.setdefault(rid, []).append(ref)

    return rid_latest, rid_all, errors


def _iter_domains(rubric: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    domains = rubric.get("domains", {})
    if not isinstance(domains, dict):
        return []
    return ((str(k), v) for k, v in domains.items() if isinstance(v, dict))


def _iter_domain_requirements(domain: dict[str, Any]) -> Iterable[dict[str, Any]]:
    reqs = domain.get("requirements", [])
    if not isinstance(reqs, list):
        return []
    return (r for r in reqs if isinstance(r, dict))


def _requirement_domain_map(rubric: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    out: dict[str, str] = {}
    errors: list[str] = []
    for domain_id, domain in _iter_domains(rubric):
        for r in _iter_domain_requirements(domain):
            rid = str(r.get("id", "") or "").strip()
            if not rid:
                continue
            if rid in out:
                errors.append(f"duplicate requirement id: {rid}")
            out[rid] = domain_id
    return out, errors


def _requirement_has_runtime_evidence(requirement: dict[str, Any]) -> bool:
    runtime_spec = requirement.get("runtime_evidence", {}) or {}
    if not isinstance(runtime_spec, dict):
        return False
    if bool(runtime_spec.get("required", False)):
        return True
    commands = runtime_spec.get("commands", []) or []
    return bool(commands)


def _evaluate_requirement(
    *,
    requirement: dict[str, Any],
    domain_id: str,
    runtime_latest: dict[str, RuntimeRunRef],
    junit: dict[str, Any] | None,
    pytest_mapping: dict[str, Any],
) -> RequirementResult:
    rid = str(requirement.get("id", "") or "").strip()
    if not rid:
        return RequirementResult(
            requirement_id="",
            domain=domain_id,
            result="UNKNOWN",
            reason="RUBRIC_INVALID",
            evidence=[],
        )

    evidence: list[EvidencePointer] = []
    if _requirement_has_runtime_evidence(requirement):
        ref = runtime_latest.get(rid)
        if not ref:
            return RequirementResult(
                requirement_id=rid,
                domain=domain_id,
                result="UNKNOWN",
                reason="NO_EVIDENCE",
                evidence=[
                    EvidencePointer(
                        kind="runtime",
                        text="missing runtime run for requirement_id",
                        keys={"requirement_id": rid},
                    )
                ],
            )

        run = ref.run
        rc = run.get("returncode", None)
        st = str(run.get("status", "") or "")
        cmd = str(run.get("command", "") or "")
        evidence.append(
            EvidencePointer(
                kind="runtime",
                text=(
                    f"runtime evidence {ref.evidence_file} run_index={ref.run_index} "
                    f"status={st!r} returncode={rc!r}"
                ),
                keys={
                    "requirement_id": rid,
                    "evidence_file": ref.evidence_file,
                    "run_index": ref.run_index,
                    "status": st,
                    "returncode": rc,
                    "command": cmd,
                },
            )
        )

        if st.lower() == "partial":
            return RequirementResult(
                requirement_id=rid,
                domain=domain_id,
                result="PARTIAL",
                reason="PARTIAL_IMPL",
                evidence=evidence,
            )

        if rc != 0 or st.lower() not in ("ok", "pass", "success"):
            return RequirementResult(
                requirement_id=rid,
                domain=domain_id,
                result="DEBT",
                reason="RUNTIME_FAIL",
                evidence=evidence,
            )

        return RequirementResult(
            requirement_id=rid,
            domain=domain_id,
            result="PASS",
            reason="",
            evidence=evidence,
        )

    # Pytest-backed requirement
    if junit is None:
        return RequirementResult(
            requirement_id=rid,
            domain=domain_id,
            result="UNKNOWN",
            reason="NO_EVIDENCE",
            evidence=[
                EvidencePointer(
                    kind="pytest",
                    text="pytest_junit.xml missing",
                    keys={"domain": domain_id},
                )
            ],
        )

    summary = _domain_test_summary(junit, pytest_mapping, domain_id)
    if summary.get("total", 0) <= 0:
        return RequirementResult(
            requirement_id=rid,
            domain=domain_id,
            result="UNKNOWN",
            reason="NO_EVIDENCE",
            evidence=[
                EvidencePointer(
                    kind="pytest",
                    text="no mapped testcases for domain",
                    keys={"domain": domain_id},
                )
            ],
        )

    failing = [
        tc
        for tc in _domain_testcases(junit, pytest_mapping, domain_id)
        if tc.get("outcome") == "fail"
    ]
    if failing:
        for tc in failing[:50]:
            evidence.append(
                EvidencePointer(
                    kind="pytest_fail",
                    text="pytest failed",
                    keys={
                        "domain": domain_id,
                        "nodeid": tc.get("nodeid"),
                        "classname": tc.get("classname"),
                        "name": tc.get("name"),
                        "file": tc.get("file"),
                    },
                )
            )
        return RequirementResult(
            requirement_id=rid,
            domain=domain_id,
            result="DEBT",
            reason="PYTEST_FAIL",
            evidence=evidence,
        )

    evidence.append(
        EvidencePointer(
            kind="pytest",
            text=(
                f"domain tests total={summary.get('total')} "
                f"pass={summary.get('pass')} skip={summary.get('skip')}"
            ),
            keys={"domain": domain_id, "summary": summary},
        )
    )
    return RequirementResult(
        requirement_id=rid,
        domain=domain_id,
        result="PASS",
        reason="",
        evidence=evidence,
    )


def _results_counts(results: Sequence[RequirementResult]) -> dict[str, int]:
    counts = {k: 0 for k in RESULT_ENUM}
    for r in results:
        if r.result in counts:
            counts[r.result] += 1
        else:
            counts["UNKNOWN"] += 1
    return counts


def _domain_counts(results: Sequence[RequirementResult]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for r in results:
        d = out.setdefault(r.domain, {k: 0 for k in RESULT_ENUM})
        if r.result in d:
            d[r.result] += 1
        else:
            d["UNKNOWN"] += 1
    return out


_RULE_RE_UNKNOWN = re.compile(r"^UNKNOWN\s*==\s*0$")
_RULE_RE_DOMAIN_NO_DEBT = re.compile(r"^domain\((?P<dom>[A-Za-z0-9_\-]+)\)\s+has\s+no\s+DEBT$")
_RULE_RE_DOMAIN_NO_PARTIAL = re.compile(
    r"^domain\((?P<dom>[A-Za-z0-9_\-]+)\)\s+has\s+no\s+PARTIAL$"
)


def _apply_profile_rules(
    *,
    profile: dict[str, Any],
    all_domains: Sequence[str],
    counts: dict[str, int],
    per_domain: dict[str, dict[str, int]],
) -> tuple[str, list[str], list[str]]:
    verdict = "PASS"
    reasons: list[str] = []
    errors: list[str] = []

    hard = profile.get("hard_requirements", [])
    if hard is None:
        hard = []
    if not isinstance(hard, list):
        errors.append("profile.hard_requirements must be a list")
        return "FAIL", reasons, errors

    for entry in hard:
        rule = None
        if isinstance(entry, dict):
            rule = entry.get("rule")
        elif isinstance(entry, str):
            rule = entry
        if not rule:
            continue
        rule_s = str(rule).strip()

        if _RULE_RE_UNKNOWN.match(rule_s):
            if counts.get("UNKNOWN", 0) != 0:
                verdict = "FAIL"
                reasons.append(f"UNKNOWN != 0 (UNKNOWN={counts.get('UNKNOWN', 0)})")
            continue

        m = _RULE_RE_DOMAIN_NO_DEBT.match(rule_s)
        if m:
            dom = m.group("dom")
            if dom not in per_domain:
                errors.append(f"profile rule references unknown domain: {dom}")
                verdict = "FAIL"
            else:
                if per_domain[dom].get("DEBT", 0) != 0:
                    verdict = "FAIL"
                    reasons.append(
                        f"domain({dom}) has DEBT (DEBT={per_domain[dom].get('DEBT', 0)})"
                    )
            continue

        m = _RULE_RE_DOMAIN_NO_PARTIAL.match(rule_s)
        if m:
            dom = m.group("dom")
            if dom not in per_domain:
                errors.append(f"profile rule references unknown domain: {dom}")
                verdict = "FAIL"
            else:
                if per_domain[dom].get("PARTIAL", 0) != 0:
                    verdict = "FAIL"
                    reasons.append(
                        f"domain({dom}) has PARTIAL (PARTIAL={per_domain[dom].get('PARTIAL', 0)})"
                    )
            continue

        errors.append(f"unrecognized profile rule: {rule_s}")
        verdict = "FAIL"

    # Variant 1 future-domain policy: all domains must be clean unless configured otherwise.
    # (This is applied outside this function so it can be optional per CLI.)
    return verdict, reasons, errors


def _apply_future_domain_policy_v1(
    *,
    all_domains: Sequence[str],
    per_domain: dict[str, dict[str, int]],
) -> tuple[str, list[str]]:
    verdict = "PASS"
    reasons: list[str] = []
    for dom in all_domains:
        dc = per_domain.get(dom, {k: 0 for k in RESULT_ENUM})
        if dc.get("UNKNOWN", 0) != 0:
            verdict = "FAIL"
            reasons.append(
                f"future-domain policy: domain({dom}) has UNKNOWN (UNKNOWN={dc.get('UNKNOWN', 0)})"
            )
        if dc.get("DEBT", 0) != 0:
            verdict = "FAIL"
            reasons.append(
                f"future-domain policy: domain({dom}) has DEBT (DEBT={dc.get('DEBT', 0)})"
            )
    return verdict, reasons


def _compose_output(
    *,
    repo: Path,
    rubric: dict[str, Any],
    rubric_path: Path,
    junit_path: Path | None,
    runtime_files: list[Path],
    profile_name: str,
    future_domain_policy: str,
    technical_results: list[RequirementResult],
    evaluator_errors: list[str],
    evaluator_warnings: list[str],
    run_timestamp: str | None,
    inputs_fingerprint: str,
) -> dict[str, Any]:
    rubric_version = int((rubric.get("meta", {}) or {}).get("schema_version", 0))
    sha = _read_git_sha(repo)

    counts = _results_counts(technical_results)
    per_domain = _domain_counts(technical_results)
    all_domains = sorted({r.domain for r in technical_results})

    profiles = ((rubric.get("global", {}) or {}).get("certification", {}) or {}).get(
        "profiles", {}
    ) or {}
    profile = profiles.get(profile_name, {})
    if not isinstance(profile, dict):
        evaluator_errors.append(f"profile not found or invalid: {profile_name}")
        profile = {}

    # Validate blockers list (if present): every blocker must exist as a requirement id in rubric.
    req_map, req_errors = _requirement_domain_map(rubric)
    evaluator_errors.extend(req_errors)
    blockers = profile.get("blockers", {})
    if isinstance(blockers, dict):
        for _dom, rid_list in blockers.items():
            if not isinstance(rid_list, list):
                continue
            for rid in rid_list:
                rid_s = str(rid).strip()
                if rid_s and rid_s not in req_map:
                    evaluator_errors.append(
                        f"profile blocker references unknown requirement_id: {rid_s}"
                    )

    verdict = "FAIL" if evaluator_errors else "PASS"
    cert_reasons: list[str] = []
    cert_errors: list[str] = []

    pr_verdict, pr_reasons, pr_errors = _apply_profile_rules(
        profile=profile,
        all_domains=all_domains,
        counts=counts,
        per_domain=per_domain,
    )
    cert_errors.extend(pr_errors)
    if pr_verdict == "FAIL":
        verdict = "FAIL"
    cert_reasons.extend(pr_reasons)

    if future_domain_policy == "v1":
        v1_verdict, v1_reasons = _apply_future_domain_policy_v1(
            all_domains=all_domains,
            per_domain=per_domain,
        )
        if v1_verdict == "FAIL":
            verdict = "FAIL"
        cert_reasons.extend(v1_reasons)
    elif future_domain_policy == "informational":
        pass
    else:
        cert_errors.append(f"unknown future-domain policy: {future_domain_policy}")
        verdict = "FAIL"

    if cert_errors:
        verdict = "FAIL"

    # Inputs list in stable order.
    input_paths = [rubric_path]
    if junit_path:
        input_paths.append(junit_path)
    input_paths.extend(sorted(runtime_files, key=lambda p: p.name))

    return {
        "audit_result_schema": AUDIT_RESULT_SCHEMA_VERSION,
        "rubric_schema_version": rubric_version,
        "profile": profile_name,
        "scope": str(profile.get("scope", "")) if isinstance(profile, dict) else "",
        "meta": {
            "timestamp": run_timestamp,
            "git_sha": sha,
            "inputs_fingerprint": inputs_fingerprint,
        },
        "inputs": {
            "rubric": _safe_relpath(repo, rubric_path),
            "pytest_junit": _safe_relpath(repo, junit_path) if junit_path else None,
            "runtime_evidence_files": [
                _safe_relpath(repo, p) for p in sorted(runtime_files, key=lambda x: x.name)
            ],
        },
        "evidence_policy": {
            "runtime_files_sort": "lexical filename",
            "runtime_run_selection": (
                "latest-seen per requirement_id (by file order, then run index)"
            ),
            "pytest_mapping": "rubric.global.pytest_domain_mapping",
        },
        "technical_summary": {
            "counts": counts,
            "per_domain": per_domain,
        },
        "certification": {
            "profile": profile_name,
            "future_domain_policy": future_domain_policy,
            "verdict": verdict,
            "reasons": cert_reasons,
            "errors": cert_errors,
        },
        "evaluator_errors": evaluator_errors,
        "evaluator_warnings": evaluator_warnings,
        "technical_results": [
            {
                "requirement_id": r.requirement_id,
                "domain": r.domain,
                "result": r.result,
                "reason": r.reason,
                "evidence": [
                    {
                        "kind": e.kind,
                        "text": e.text,
                        "keys": e.keys,
                    }
                    for e in r.evidence
                ],
            }
            for r in sorted(technical_results, key=lambda x: x.requirement_id)
        ],
        "publication": {
            "git_auto": None,  # populated later
            "status": None,
            "reason": None,
            "commit_sha": None,
            "pushed": None,
            "remote": None,
            "branch": None,
        },
    }


def _yaml_dump_stable(data: dict[str, Any]) -> str:
    out = yaml.safe_dump(
        data,
        sort_keys=True,
        allow_unicode=False,
    )
    return out if isinstance(out, str) else str(out)


def _ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suf = path.suffix
    parent = path.parent
    for i in range(1, 1000):
        cand = parent / f"{stem}_{i}{suf}"
        if not cand.exists():
            return cand
    raise RuntimeError(f"unable to allocate unique output path: {path}")


def _build_default_output_path(
    results_dir: Path,
    profile_name: str,
    run_timestamp: str | None,
    inputs_fingerprint: str,
) -> Path:
    ts = run_timestamp or "unknown_ts"
    safe_ts = re.sub(r"[^0-9A-Za-z_.:-]+", "_", ts)
    return results_dir / f"audit_{profile_name}_{safe_ts}_{inputs_fingerprint}.yaml"


def _git_state_allows_publish(repo: Path) -> tuple[bool, str]:
    # Do not publish during ongoing git operations.
    git_dir = repo / ".git"
    if not git_dir.exists():
        return False, "not a git checkout"
    if (git_dir / "MERGE_HEAD").exists():
        return False, "merge in progress"
    if (git_dir / "CHERRY_PICK_HEAD").exists():
        return False, "cherry-pick in progress"
    if (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists():
        return False, "rebase in progress"

    try:
        p = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo,
            text=True,
            capture_output=True,
        )
        br = (p.stdout or "").strip()
        if p.returncode != 0:
            return False, "unable to detect current branch"
        if br == "HEAD" or not br:
            return False, "detached HEAD"
    except Exception:
        return False, "unable to detect git branch"

    return True, "ok"


def _git_publish_created_files(
    *,
    repo: Path,
    created_files: Sequence[Path],
    message: str,
    remote: str,
    branch: str,
    push: bool,
    no_verify: bool,
) -> tuple[str, str | None, str | None]:
    """Publish ONLY created_files.

    Avoid alternate-index (GIT_INDEX_FILE) publishing. Alternate-index commits can advance HEAD
    while leaving the primary index untouched, which can present as staged deletes +
    untracked files.

    We publish using the primary index with a targeted commit:
      - git add -- <paths>
      - git commit --only -m ... -- <paths>
      - optional git push
    """
    ok, why = _git_state_allows_publish(repo)
    if not ok:
        return "skipped", None, why

    rels: list[str] = []
    for p in created_files:
        rels.append(_safe_relpath(repo, p))

    add = subprocess.run(
        ["git", "add", "--", *rels],
        cwd=repo,
        text=True,
        capture_output=True,
    )
    if add.returncode != 0:
        msg = (add.stderr or add.stdout or "").strip()
        return "error", None, f"git add failed: {msg}"

    commit_cmd = ["git", "commit", "--only", "-m", message]
    if no_verify:
        commit_cmd.append("--no-verify")
    commit_cmd.extend(["--", *rels])
    commit = subprocess.run(commit_cmd, cwd=repo, text=True, capture_output=True)
    if commit.returncode != 0:
        msg = (commit.stderr + "\\n" + commit.stdout).strip()
        low = msg.lower()
        if "nothing to commit" in low or "no changes" in low:
            return "ok", None, None
        return "error", None, f"git commit failed: {msg}"

    sha = _read_git_sha(repo)

    if push:
        pushp = subprocess.run(
            ["git", "push", remote, branch],
            cwd=repo,
            text=True,
            capture_output=True,
        )
        if pushp.returncode != 0:
            msg = (pushp.stderr or pushp.stdout or "").strip()
            return "error", sha, f"git push failed: {msg}"

    return "ok", sha, None


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="evaluate_audit", add_help=True)
    ap.add_argument("--repo", default=".", help="Repository root (default: .)")
    ap.add_argument(
        "--rubric",
        default="audit/audit_rubric.yaml",
        help="Rubric YAML path (default: audit/audit_rubric.yaml)",
    )
    ap.add_argument(
        "--results-dir",
        default="audit/results",
        help="Results directory (default: audit/results)",
    )
    ap.add_argument(
        "--profile",
        default="C3_ALL_v5",
        help="Certification profile to apply (default: C3_ALL_v5)",
    )
    ap.add_argument(
        "--future-domain-policy",
        default="v1",
        choices=list(FUTURE_DOMAIN_POLICIES),
        help="How to treat domains not explicitly mentioned by profile rules (default: v1)",
    )
    ap.add_argument(
        "--out",
        default=None,
        help="Explicit output YAML path (must not already exist)",
    )
    ap.add_argument(
        "--no-git",
        action="store_true",
        help="Disable git commit/push automation (default: enabled)",
    )
    ap.add_argument(
        "--git-no-push",
        action="store_true",
        help="Commit but do not push (default: push)",
    )
    ap.add_argument("--git-remote", default="origin", help="Remote name for push (default: origin)")
    ap.add_argument(
        "--git-branch",
        default=None,
        help="Branch name for push (default: current branch)",
    )
    ap.add_argument("--git-no-verify", action="store_true", help="Pass --no-verify to git commit")
    args = ap.parse_args(list(argv) if argv is not None else None)

    repo = Path(args.repo).resolve()
    rubric_path = (repo / args.rubric).resolve()
    results_dir = (repo / args.results_dir).resolve()
    profile_name = str(args.profile).strip()

    evaluator_errors: list[str] = []
    evaluator_warnings: list[str] = []

    if not rubric_path.exists():
        print(f"error: rubric not found: {rubric_path}")
        return 2
    if not results_dir.exists():
        print(f"error: results dir not found: {results_dir}")
        return 2

    rubric = _read_yaml(rubric_path)
    pytest_mapping = (rubric.get("global", {}) or {}).get("pytest_domain_mapping", {}) or {}
    runtime_files = _list_runtime_evidence_files(results_dir)
    junit_path = results_dir / "pytest_junit.xml"
    junit: dict[str, Any] | None = None
    if junit_path.exists():
        try:
            junit = _parse_pytest_junit(junit_path)
        except Exception as e:
            evaluator_errors.append(f"failed to parse pytest_junit.xml: {e}")

    # Load runtime evidence runs and validate ids against rubric.
    runtime_latest, _runtime_all, runtime_load_errors = _load_runtime_runs(runtime_files)
    evaluator_errors.extend(runtime_load_errors)

    req_map, req_map_errors = _requirement_domain_map(rubric)
    evaluator_errors.extend(req_map_errors)

    for rid in sorted(runtime_latest.keys()):
        if rid not in req_map:
            evaluator_errors.append(f"runtime evidence references unknown requirement_id: {rid}")

    # Determine deterministic timestamp from inputs.
    ts_candidates: list[str] = []
    if junit and junit.get("suite_timestamp"):
        ts_candidates.append(str(junit.get("suite_timestamp")))
    for p in sorted(runtime_files, key=lambda x: x.name):
        try:
            data = _read_yaml(p)
            meta = data.get("meta", {}) if isinstance(data, dict) else {}
            gen = meta.get("generated_at")
            if gen:
                ts_candidates.append(str(gen))
        except Exception:
            continue
    run_timestamp = _max_timestamp(ts_candidates)

    # Evaluate all rubric requirements, domain-by-domain, including future domains.
    technical_results: list[RequirementResult] = []
    all_domain_ids = sorted([dom_id for dom_id, _ in _iter_domains(rubric)])
    if not all_domain_ids:
        evaluator_errors.append("rubric contains no domains")

    for dom_id, dom in _iter_domains(rubric):
        for req in _iter_domain_requirements(dom):
            rr = _evaluate_requirement(
                requirement=req,
                domain_id=dom_id,
                runtime_latest=runtime_latest,
                junit=junit,
                pytest_mapping=pytest_mapping,
            )
            if rr.requirement_id:
                technical_results.append(rr)
            else:
                evaluator_errors.append(
                    f"invalid requirement in rubric domain {dom_id}: missing id"
                )

    # Inputs fingerprint for stable output naming.
    input_paths: list[Path] = [rubric_path]
    if junit_path.exists():
        input_paths.append(junit_path)
    input_paths.extend(sorted(runtime_files, key=lambda p: p.name))
    inputs_fingerprint = _stable_inputs_fingerprint(repo, input_paths)

    output = _compose_output(
        repo=repo,
        rubric=rubric,
        rubric_path=rubric_path,
        junit_path=junit_path if junit_path.exists() else None,
        runtime_files=runtime_files,
        profile_name=profile_name,
        future_domain_policy=str(args.future_domain_policy),
        technical_results=technical_results,
        evaluator_errors=evaluator_errors,
        evaluator_warnings=evaluator_warnings,
        run_timestamp=run_timestamp,
        inputs_fingerprint=inputs_fingerprint,
    )

    # Output path.
    if args.out:
        out_path = (repo / str(args.out)).resolve()
        if out_path.exists():
            print(f"error: --out already exists: {out_path}")
            return 2
    else:
        out_path = _build_default_output_path(
            results_dir,
            profile_name,
            run_timestamp,
            inputs_fingerprint,
        )
        out_path = _ensure_unique_path(out_path)

    out_text = _yaml_dump_stable(output)
    out_path.write_text(out_text, encoding="utf-8")
    created_files = [out_path]

    # Publication (git) - default ON.
    if args.no_git:
        output["publication"].update(
            {
                "git_auto": False,
                "status": "skipped",
                "reason": "--no-git",
                "commit_sha": None,
                "pushed": None,
                "remote": None,
                "branch": None,
            }
        )
    else:
        # Resolve current branch if not given.
        branch = args.git_branch
        if not branch:
            try:
                proc = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=repo,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                branch = (proc.stdout or "").strip() if proc.returncode == 0 else ""
            except Exception:
                branch = ""
        if not branch or branch == "HEAD":
            output["publication"].update(
                {
                    "git_auto": True,
                    "status": "skipped",
                    "reason": "detached HEAD or unknown branch",
                    "commit_sha": None,
                    "pushed": None,
                    "remote": args.git_remote,
                    "branch": branch or None,
                }
            )
        else:
            push = not bool(args.git_no_push)
            st, commit_sha, err = _git_publish_created_files(
                repo=repo,
                created_files=created_files,
                message=f"audit: certify {profile_name} @ {run_timestamp or 'unknown_ts'}",
                remote=str(args.git_remote),
                branch=str(branch),
                push=push,
                no_verify=bool(args.git_no_verify),
            )
            output["publication"].update(
                {
                    "git_auto": True,
                    "status": st,
                    "reason": err,
                    "commit_sha": commit_sha,
                    "pushed": bool(push) if st == "ok" else None,
                    "remote": args.git_remote,
                    "branch": branch,
                }
            )

    # Rewrite file with final publication details (deterministic for same inputs and flags).
    out_path.write_text(_yaml_dump_stable(output), encoding="utf-8")
    # Follow-up commit: the tool rewrites the YAML after publishing to record publication status.
    # Commit that rewrite so the working tree stays clean.
    if (
        output.get("publication", {}).get("git_auto")
        and output.get("publication", {}).get("status") == "ok"
    ):
        rel = _safe_relpath(repo, out_path)
        subprocess.run(["git", "add", "--", rel], cwd=repo, text=True, capture_output=True)
        cmd = [
            "git",
            "commit",
            "--only",
            "-m",
            f"audit: record publication status {profile_name} @ {run_timestamp or 'unknown_ts'}",
        ]
        if bool(args.git_no_verify):
            cmd.append("--no-verify")
        cmd.extend(["--", rel])
        c2 = subprocess.run(cmd, cwd=repo, text=True, capture_output=True)
        if c2.returncode == 0 and not bool(args.git_no_push):
            subprocess.run(
                ["git", "push", str(args.git_remote), str(branch)],
                cwd=repo,
                text=True,
                capture_output=True,
            )

    print(f"ok: wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
