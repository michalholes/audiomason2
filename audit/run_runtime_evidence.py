#!/usr/bin/env python3
"""
Generate runtime evidence by executing commands declared in a rubric YAML and writing a single
YAML report.

This tool is audit-only and MUST be non-destructive: it only runs CLI commands and captures outputs.

Canonical rubric file (stable name):
  audit/audit_rubric.yaml

Usage:
  python3 audit/run_runtime_evidence.py --repo . --rubric audit/audit_rubric.yaml

Optional:
  python3 audit/run_runtime_evidence.py --repo . --rubric audit/audit_rubric.yaml \
    --out audit/results/runtime_evidence_manual.yaml
  python3 audit/run_runtime_evidence.py --repo . --rubric audit/audit_rubric.yaml --timeout 60
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

AUDIT_RESULT_SCHEMA = "am2.audit.v1"
AUDIT_REGISTRY_SCHEMA = "am2.audit.registry.v1"


def _git_commit_and_optional_push(repo: Path, out_path: Path, *, message: str, push: bool) -> int:
    # Targeted automation: never runs "git add .".
    if not (repo / ".git").exists():
        print("[warn] --git-commit requested but repo is not a git checkout")
        return 0

    rel = str(out_path.relative_to(repo))
    # Stage only the output file.
    add = subprocess.run(["git", "add", "--", rel], cwd=repo, text=True, capture_output=True)
    if add.returncode != 0:
        print("[warn] git add failed:", add.stderr.strip() or add.stdout.strip())
        return 2

    commit = subprocess.run(
        ["git", "commit", "-m", message, "--", rel], cwd=repo, text=True, capture_output=True
    )
    if commit.returncode != 0:
        # "nothing to commit" is not a hard error in this workflow.
        msg = (commit.stderr + "\n" + commit.stdout).strip()
        if "nothing to commit" in msg.lower() or "no changes" in msg.lower():
            print("[ok] git commit: nothing to commit for", rel)
            return 0
        print("[warn] git commit failed:", msg)
        return 2

    print("[ok] git commit:", (commit.stdout.strip() or "(no stdout)"))

    if push:
        pushp = subprocess.run(["git", "push"], cwd=repo, text=True, capture_output=True)
        if pushp.returncode != 0:
            print("[warn] git push failed:", (pushp.stderr.strip() or pushp.stdout.strip()))
            return 2
        print("[ok] git push")
    return 0


def _expects_audit_protocol(cmd: str) -> bool:
    # Commands that MUST emit machine-readable audit output.
    s = cmd
    if " --selftest" in s:
        return True
    if " -m audiomason plugins" in s and (" --list" in s or " --validate" in s):
        return True
    if " -m audiomason audit" in s and " --list-domains" in s:
        return True
    return False


def _load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))


def _now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def _short_env_snapshot() -> dict[str, str]:
    keys = [
        "PATH",
        "PYTHONPATH",
        "VIRTUAL_ENV",
        "AUDIOMASON_LOG_MODE",
        "AUDIOMASON_LOG_PATH",
        "AUDIOMASON_OUTPUT_DIR",
    ]
    out: dict[str, str] = {}
    for k in keys:
        if k in os.environ:
            out[k] = os.environ[k]
    return out


def _collect_required_commands(rubric: dict[str, Any]) -> list[tuple[str, str]]:
    """
    Returns list of (requirement_id, command_string) for requirements where
    runtime_evidence.required is True.
    De-duplicates exact same command strings globally while preserving first-seen order.
    """
    seen_cmds: set[str] = set()
    out: list[tuple[str, str]] = []

    domains = rubric.get("domains", {})
    for dom in domains.values():
        for req in dom.get("requirements", []):
            rid = str(req.get("id", "")).strip()
            rt = req.get("runtime_evidence", {}) or {}
            if not bool(rt.get("required", False)):
                continue
            cmds = rt.get("commands", []) or []
            for c in cmds:
                c = str(c).strip()
                if not c or c in seen_cmds:
                    continue
                seen_cmds.add(c)
                out.append((rid or "UNKNOWN", c))
    return out


def _run_one(*, repo: Path, rid: str, cmd: str, timeout_s: int) -> dict[str, Any]:
    argv = shlex.split(cmd)
    started = time.time()
    try:
        proc = subprocess.run(
            argv,
            cwd=str(repo),
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        status = "ok"
        rc: int | None = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
    except subprocess.TimeoutExpired as e:
        status = "timeout"
        rc = None
        stdout = (
            e.stdout
            if isinstance(e.stdout, str)
            else (e.stdout.decode("utf-8", errors="replace") if e.stdout else "")
        )
        stderr = (
            e.stderr
            if isinstance(e.stderr, str)
            else (e.stderr.decode("utf-8", errors="replace") if e.stderr else "")
        )
    except FileNotFoundError as e:
        status = "exec_error"
        rc = None
        stdout = ""
        stderr = f"{type(e).__name__}: {e}"
    except Exception as e:
        status = "exec_error"
        rc = None
        stdout = ""
        stderr = f"{type(e).__name__}: {e}"

    ended = time.time()
    return {
        "requirement_id": rid,
        "command": cmd,
        "argv": argv,
        "cwd": str(repo),
        "status": status,
        "returncode": rc,
        "duration_seconds": round(ended - started, 6),
        "stdout": stdout,
        "stderr": stderr,
    }


def _parse_stdout(stdout: str) -> tuple[Any | None, str | None]:
    s = (stdout or "").strip()
    if not s:
        return None, "empty stdout"
    try:
        return yaml.safe_load(s), None
    except Exception:
        try:
            return json.loads(s), None
        except Exception as e:  # noqa: BLE001
            return None, f"parse error: {type(e).__name__}: {e}"


def _validate_protocol(parsed: Any | None) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not isinstance(parsed, dict):
        failures.append("parsed is not a mapping")
        return False, failures

    sv = parsed.get("schema_version")
    if sv != AUDIT_RESULT_SCHEMA:
        failures.append(f"schema_version mismatch: {sv!r}")
    for k in ("tool", "domain", "subject", "status", "checks"):
        if k not in parsed:
            failures.append(f"missing field: {k}")
    checks = parsed.get("checks")
    if isinstance(checks, list):
        if len(checks) == 0:
            failures.append("checks is empty")
    else:
        failures.append("checks is not a list")

    return len(failures) == 0, failures


def _discover_plan(*, repo: Path, python: str, timeout_s: int) -> list[tuple[str, str]]:
    cmd = f"{python} -m audiomason audit --list-domains --format yaml"
    run = _run_one(repo=repo, rid="AUDIT-REGISTRY", cmd=cmd, timeout_s=timeout_s)
    parsed, perr = _parse_stdout(run["stdout"])
    if perr:
        raise RuntimeError(f"Discovery failed: {perr}")
    if not isinstance(parsed, dict) or parsed.get("schema_version") != AUDIT_REGISTRY_SCHEMA:
        raise RuntimeError("Discovery failed: invalid registry schema_version")
    domains = parsed.get("domains")
    if not isinstance(domains, list):
        raise RuntimeError("Discovery failed: domains is not a list")

    plan: list[tuple[str, str]] = []
    seen: set[str] = set()
    for d in domains:
        if not isinstance(d, dict):
            continue
        domain = str(d.get("domain", "")).strip()
        cli_name = str(d.get("cli_name", "")).strip()
        caps = d.get("capabilities", [])
        if not domain or not cli_name or not isinstance(caps, list):
            continue

        if "selftest" in caps:
            c = f"{python} -m audiomason {cli_name} --selftest --format yaml"
            if c not in seen:
                seen.add(c)
                plan.append((f"{domain}.selftest", c))

        if "plugins_list" in caps:
            c = f"{python} -m audiomason plugins --list --format yaml"
            if c not in seen:
                seen.add(c)
                plan.append((f"{domain}.plugins.list", c))

        if "plugins_validate" in caps:
            c = f"{python} -m audiomason plugins --validate --format yaml"
            if c not in seen:
                seen.add(c)
                plan.append((f"{domain}.plugins.validate", c))

    return plan


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--repo", required=True, help="Path to repo root (contains src/ or pyproject.toml)."
    )
    ap.add_argument(
        "--rubric",
        default="audit/audit_rubric.yaml",
        help="Path to rubric YAML (rubric mode). Default: audit/audit_rubric.yaml",
    )
    ap.add_argument(
        "--discover", action="store_true", help="Discover domains via CLI and run selftests."
    )
    ap.add_argument(
        "--python", default=sys.executable, help="Python executable to use for commands."
    )
    ap.add_argument(
        "--out",
        default="",
        help="Output YAML file. Default: audit/results/runtime_evidence_TIMESTAMP.yaml",
    )
    ap.add_argument("--timeout", type=int, default=180, help="Per-command timeout in seconds.")
    ap.add_argument("--max-commands", type=int, default=0, help="Optional limit (0 = no limit).")
    ap.add_argument(
        "--git-commit",
        action="store_true",
        help="Commit only the generated output file (no git add .).",
    )
    ap.add_argument(
        "--git-push", action="store_true", help="Push after --git-commit (works with dirty tree)."
    )
    ap.add_argument(
        "--git-message",
        default="audit: runtime evidence",
        help="Commit message used with --git-commit.",
    )
    args = ap.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    if not repo.exists():
        print(f"[fatal] repo not found: {repo}", file=sys.stderr)
        return 2

    if not args.discover and not args.rubric.strip():
        print("[fatal] must provide --rubric or --discover", file=sys.stderr)
        return 2

    if args.discover:
        try:
            commands = _discover_plan(repo=repo, python=args.python, timeout_s=args.timeout)
        except Exception as e:  # noqa: BLE001
            print(f"[fatal] discovery failed: {type(e).__name__}: {e}", file=sys.stderr)
            return 2
    else:
        rubric_path = Path(args.rubric).expanduser().resolve()
        if not rubric_path.exists():
            print(f"[fatal] rubric not found: {rubric_path}", file=sys.stderr)
            return 2
        rubric = _load_yaml(rubric_path)
        commands = _collect_required_commands(rubric)

    if args.max_commands and args.max_commands > 0:
        commands = commands[: args.max_commands]

    if not commands:
        print("[fatal] no commands to run", file=sys.stderr)
        return 2

    if args.out.strip():
        out_path = Path(args.out).expanduser().resolve()
    else:
        out_dir = repo / "audit" / "results"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"runtime_evidence_{_now_stamp()}.yaml"

    header: dict[str, Any] = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "repo": str(repo),
            "rubric": str(args.rubric) if args.rubric else "",
            "mode": "discover" if args.discover else "rubric",
            "python": str(args.python),
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "env": _short_env_snapshot(),
        },
        "commands_total": len(commands),
        "runs": [],
        "summary": {"acceptance_pass": 0, "acceptance_fail": 0},
    }

    runs: list[dict[str, Any]] = []
    for rid, cmd in commands:
        r = _run_one(repo=repo, rid=rid, cmd=cmd, timeout_s=args.timeout)
        parsed, perr = _parse_stdout(r["stdout"])
        r["parsed"] = parsed
        r["parse_error"] = perr

        failures: list[str] = []
        if r["status"] != "ok":
            failures.append(f"exec status: {r['status']}")
        if r["returncode"] != 0:
            failures.append(f"returncode: {r['returncode']}")

        protocol_expected = _expects_audit_protocol(cmd)
        protocol_observed = isinstance(parsed, dict) and parsed.get("schema_version") in (
            AUDIT_RESULT_SCHEMA,
            AUDIT_REGISTRY_SCHEMA,
        )
        r["protocol"] = {"expected": protocol_expected, "observed": bool(protocol_observed)}

        if protocol_expected:
            if perr:
                failures.append(perr)
            ok_proto, pf = _validate_protocol(parsed)
            if not ok_proto:
                failures.extend(pf)
        else:
            # Optional: do not fail on parse errors for legacy commands (e.g. --help).
            if isinstance(parsed, dict) and parsed.get("schema_version") == AUDIT_RESULT_SCHEMA:
                ok_proto, pf = _validate_protocol(parsed)
                if not ok_proto:
                    failures.extend(pf)

        accepted = len(failures) == 0
        r["acceptance"] = {"pass": accepted, "failures": failures}
        if accepted:
            header["summary"]["acceptance_pass"] += 1
        else:
            header["summary"]["acceptance_fail"] += 1

        runs.append(r)

    header["runs"] = runs

    out_path.write_text(yaml.safe_dump(header, sort_keys=False, width=120), encoding="utf-8")
    print(f"[ok] wrote: {out_path}")

    if args.git_commit:
        rc = _git_commit_and_optional_push(
            repo, out_path, message=args.git_message, push=bool(args.git_push)
        )
        if rc != 0:
            return rc

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
