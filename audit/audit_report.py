#!/usr/bin/env python3
"""audit/audit_report.py

One-shot audit command.

Goal: run all required evidence collection and print a SHORT human delta summary
to stdout (intended for frequent/automatic runs, e.g. after each commit).

Pipeline:
1) Generate runtime evidence (audit/run_runtime_evidence.py)
2) Run pytest inside venv and generate JUnit evidence (audit/results/pytest_junit.xml)
3) Evaluate audit (audit/evaluate_audit.py)
4) Summarize delta and write long report (audit/summarize_audit.py -> audit/summary.md)

Notes:
- Git auto publish is ON by default (opt-out --no-git).
- This tool is an orchestrator; it may run pytest and runtime commands.
- By default, stdout is minimal: only the SHORT summary produced by summarize_audit.py.
  Use --verbose for step-by-step logs.

Usage:
  python3 audit/audit_report.py
  python3 audit/audit_report.py --profile C3_ALL_v5
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _detect_repo_root() -> Path:
    try:
        p = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if p.returncode == 0:
            s = (p.stdout or "").strip()
            if s:
                return Path(s).resolve()
    except Exception:
        pass
    return Path(__file__).resolve().parents[1]


def _load_report_config(repo_root: Path, config_path: str | None) -> dict[str, Any]:
    if config_path:
        cfg_path = (repo_root / config_path).resolve()
    else:
        cfg_path = (repo_root / "audit" / "audit_report_config.yaml").resolve()

    if not cfg_path.exists():
        return {}

    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _resolve_profile(cli_profile: str | None, cfg: dict[str, Any]) -> str:
    if cli_profile:
        return cli_profile

    v = cfg.get("default_profile")
    if isinstance(v, str) and v.strip():
        return v.strip()

    return "C3_ALL_v5"


def _resolve_venv_python(repo: Path) -> Path:
    # Prefer repo-local venvs.
    candidates = [repo / ".venv" / "bin" / "python", repo / "venv" / "bin" / "python"]
    for c in candidates:
        # IMPORTANT: do NOT use Path.resolve() here; it would follow symlinks and
        # collapse the venv wrapper to /usr/bin/python*, bypassing venv site-packages.
        vpy = c.absolute()
        if vpy.exists() and os.access(vpy, os.X_OK):
            return vpy

    # If caller already runs inside the repo venv, accept that too.
    exe = Path(sys.executable).absolute()
    for vdir in (repo / ".venv", repo / "venv"):
        try:
            vdir_r = vdir.resolve()
        except Exception:
            continue
        if str(exe).startswith(str(vdir_r) + "/"):
            return exe

    raise RuntimeError(
        "No venv python found. Create/repair repo venv at .venv (or venv) and rerun. "
        "Expected executable at .venv/bin/python."
    )


def _safe_relpath(repo: Path, p: Path) -> str:
    try:
        return str(p.relative_to(repo))
    except Exception:
        return str(p)


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


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "One-shot audit: collect evidence, evaluate, summarize, print SHORT human report."
        ),
    )
    ap.add_argument(
        "--profile",
        required=False,
        help="Certification profile name (overrides config), e.g. C3_ALL_v5",
    )
    ap.add_argument(
        "--config",
        required=False,
        help="Config path relative to repo root (default: audit/audit_report_config.yaml)",
    )
    ap.add_argument(
        "--results-dir",
        default="audit/results",
        help="Results directory (default: audit/results)",
    )
    ap.add_argument("--no-git", action="store_true", help="Disable git publish for all steps.")
    ap.add_argument("--git-no-push", action="store_true", help="Commit but do not push.")
    ap.add_argument("--git-no-verify", action="store_true", help="Pass --no-verify to git commit.")
    ap.add_argument("--git-remote", default="origin", help="Git remote for push (default: origin)")
    ap.add_argument("--git-branch", default=None, help="Branch to push (default: current branch)")
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Print step outputs (default is minimal stdout).",
    )
    ns = ap.parse_args(argv)

    repo = _detect_repo_root()
    cfg = _load_report_config(repo, ns.config)
    profile = _resolve_profile(ns.profile, cfg)
    results_dir = (repo / ns.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)

    try:
        py = _resolve_venv_python(repo)
    except Exception as e:
        print(f"error: {e}")
        return 2

    if ns.verbose:
        # Make it explicit which interpreter will run all steps.
        print(f"venv_python={py}")
        # Show pytest version from that interpreter (helps diagnose accidental system pytest).
        rc_v, out_v = _run([str(py), "-m", "pytest", "--version"], cwd=repo)
        if out_v.strip():
            print(out_v.strip())

    def vlog(title: str, body: str) -> None:
        if not ns.verbose:
            return
        print("\n" + ("=" * 80))
        print(title)
        print("=" * 80)
        if body.strip():
            print(body.strip())

    # 1) runtime evidence
    cmd = [str(py), "audit/run_runtime_evidence.py", "--repo", str(repo)]
    if not ns.no_git:
        cmd.append("--git-commit")
        if not ns.git_no_push:
            cmd.append("--git-push")
        cmd.extend(["--git-message", f"audit: runtime evidence ({profile})"])
    rc, out = _run(cmd, cwd=repo)
    vlog("1) Runtime evidence", out)
    if rc != 0:
        if not ns.verbose and out.strip():
            print(out.strip())
        print(f"error: runtime evidence failed (exit={rc})")
        return 2

    # 2) pytest (JUnit) - controlled output path, venv-safe
    junit_path = (results_dir / "pytest_junit.xml").resolve()
    cmd = [str(py), "-m", "pytest", "--junitxml", str(junit_path)]
    rc, out = _run(cmd, cwd=repo)
    vlog("2) Pytest evidence (JUnit)", out)
    if rc != 0:
        if not ns.verbose and out.strip():
            print(out.strip())
        print(f"error: pytest failed (exit={rc})")
        return 2

    # Publish JUnit evidence (targeted) so the run leaves a clean tree.
    if not ns.no_git and junit_path.exists():
        status, detail = _git_publish_files(
            repo=repo,
            files=[junit_path],
            message=f"audit: pytest evidence (JUnit) ({profile})",
            remote=str(ns.git_remote),
            branch=ns.git_branch,
            push=(not ns.git_no_push),
            no_verify=bool(ns.git_no_verify),
        )
        if status == "error":
            print(f"error: git publish failed for pytest_junit.xml: {detail}")
            return 2

    # 3) evaluator
    cmd = [str(py), "audit/evaluate_audit.py", "--profile", profile]
    if ns.no_git:
        cmd.append("--no-git")
    if ns.git_no_push:
        cmd.append("--git-no-push")
    if ns.git_no_verify:
        cmd.append("--git-no-verify")
    rc, out = _run(cmd, cwd=repo)
    vlog("3) Audit evaluation", out)
    if rc != 0:
        if not ns.verbose and out.strip():
            print(out.strip())
        print(f"error: evaluator failed (exit={rc})")
        return 2

    # 4) summarizer (prints SHORT report; also writes audit/summary.md)
    cmd = [
        str(py),
        "audit/summarize_audit.py",
        "--profile",
        profile,
        "--results-dir",
        str(results_dir),
    ]
    if ns.no_git:
        cmd.append("--no-git")
    if ns.git_no_push:
        cmd.append("--git-no-push")
    if ns.git_no_verify:
        cmd.append("--git-no-verify")
    if ns.verbose:
        cmd.append("--print-files")
    rc, out = _run(cmd, cwd=repo)
    # In default mode, stdout should be ONLY the short summary.
    print(out.rstrip())
    if rc != 0:
        print(f"error: summarizer failed (exit={rc})")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
