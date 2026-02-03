from __future__ import annotations

import argparse
import fnmatch
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Expect:
    ok: bool
    stage: str | None = None
    category: str | None = None


@dataclass
class WorkspacePolicy:
    clean_before: bool
    clean_after: bool


def _load(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)


def _append(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(s)


def _banner(p: Path, title: str) -> None:
    line = "=" * 80
    _append(p, f"{line}\n{title}\n{line}\n\n")


def _tail(p: Path, n: int = 160) -> str:
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:]) + ("\n" if lines else "")
    except FileNotFoundError:
        return ""


def _safe_name(s: str) -> str:
    # Keep filenames predictable and portable.
    out = []
    for ch in s:
        if ch.isalnum() or ch in ("-", "_", "."):
            out.append(ch)
        else:
            out.append("_")
    return "".join(out).strip("_") or "step"


def _git_snapshot(repo_dir: Path) -> str:
    # Best-effort diagnostics. These are not required for correctness but help explain NOOP/SCOPE outcomes.
    if not (repo_dir / ".git").exists():
        return ""
    parts: list[str] = []
    try:
        p = _run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo_dir)
        parts.append("$ git status --porcelain --untracked-files=all\n")
        parts.append(p.stdout + p.stderr)
    except Exception as e:  # pragma: no cover
        parts.append(f"(git status failed: {e})\n")
    try:
        p = _run(["git", "diff", "--name-only"], cwd=repo_dir)
        parts.append("\n$ git diff --name-only\n")
        parts.append(p.stdout + p.stderr)
    except Exception as e:  # pragma: no cover
        parts.append(f"(git diff failed: {e})\n")
    return "".join(parts)


def _parse_fingerprint(t: str) -> tuple[str | None, str | None]:
    stage = None
    cat = None
    for line in t.splitlines():
        s = line.strip()
        if s.startswith("- stage:"):
            stage = s.split(":", 1)[1].strip()
        if s.startswith("- category:"):
            cat = s.split(":", 1)[1].strip()
    return stage, cat


def _expect(obj: dict[str, Any]) -> Expect:
    return Expect(ok=bool(obj.get("ok", False)), stage=obj.get("stage"), category=obj.get("category"))


def _ws_policy(suite_ws: dict[str, Any] | None, step_ws: dict[str, Any] | None) -> WorkspacePolicy:
    base = suite_ws or {}
    over = step_ws or {}
    clean_before = bool(over.get("clean_before", base.get("clean_before", True)))
    clean_after = bool(over.get("clean_after", base.get("clean_after", True)))
    return WorkspacePolicy(clean_before=clean_before, clean_after=clean_after)


def _workspace_dir(issue: str) -> Path:
    return REPO_ROOT / "patches" / "workspaces" / f"issue_{issue}"


def _clean_workspace(issue: str) -> None:
    shutil.rmtree(_workspace_dir(issue), ignore_errors=True)


def _fmt_progress(i: int, total: int, name: str, status: str) -> str:
    pct = int((i / total) * 100) if total else 100
    return f"{i:02d}/{total:02d} {pct:3d}% {name} ... {status}"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--keep-workspace", action="store_true")
    ap.add_argument("--keep-workspace-on-fail", action="store_true")
    ap.add_argument("--ci", action="store_true", help="CI mode: never run kind=patch steps")
    ap.add_argument("--include", action="append", default=[], help="Run only steps whose name matches these glob patterns (can be repeated; comma-separated allowed)")
    ap.add_argument("--exclude", action="append", default=[], help="Skip steps whose name matches these glob patterns (can be repeated; comma-separated allowed)")
    ap.add_argument("--use-include", dest="use_include", action="store_true", default=None, help="Enable include filtering (overrides cfg)")
    ap.add_argument("--no-include", dest="use_include", action="store_false", default=None, help="Disable include filtering (overrides cfg)")
    ap.add_argument("--use-exclude", dest="use_exclude", action="store_true", default=None, help="Enable exclude filtering (overrides cfg)")
    ap.add_argument("--no-exclude", dest="use_exclude", action="store_false", default=None, help="Disable exclude filtering (overrides cfg)")
    ns, _ = ap.parse_known_args(argv)
    data = _load(REPO_ROOT / "badguys" / "suite.toml")
    suite = data["suite"]
    issue = str(suite["issue_id"])
    # Snapshot archived patch scripts so we can delete suite-created archives at the end.
    succ_dir = REPO_ROOT / "patches" / "successful"
    unsucc_dir = REPO_ROOT / "patches" / "unsuccessful"
    _succ_before = {p.resolve() for p in succ_dir.glob("*.py")} if succ_dir.exists() else set()
    _unsucc_before = {p.resolve() for p in unsucc_dir.glob("*.py")} if unsucc_dir.exists() else set()
    logs_dir = REPO_ROOT / "patches" / "logs"
    _logs_before = {p.resolve() for p in logs_dir.glob("*")} if logs_dir.exists() else set()
    # Track temp branch name (used by branch tests) so we can force-return to main when needed.
    tmp_branch = f"badguys/tmp-branch-{issue}"

    runner_argv = shlex.split(str(suite["runner"]))
    patch_dst = REPO_ROOT / str(suite["patch_dst"])
    master_log = REPO_ROOT / str(suite["master_log"])
    # Clean step logs directory every run (prevents accumulation of stale logs)
    step_logs_dir = REPO_ROOT / "patches" / "badguys_step_logs"
    if step_logs_dir.exists():
        shutil.rmtree(step_logs_dir)
    step_logs_dir.mkdir(parents=True, exist_ok=True)
    suite_ws = data.get("workspace")

    # Clear master log every run
    if master_log.exists():
        master_log.unlink()
    master_log.parent.mkdir(parents=True, exist_ok=True)
    master_log.write_text("", encoding="utf-8")

    def _split_patterns(values: list[str]) -> list[str]:
        out: list[str] = []
        for v in values:
            for part in str(v).split(","):
                s = part.strip()
                if s:
                    out.append(s)
        return out
    cfg_filters = data.get("filters", {}) if isinstance(data.get("filters", {}), dict) else {}

    def _bool_or_none(v: object) -> bool | None:
        if v is None:
            return None
        if isinstance(v, bool):
            return v
        if isinstance(v, int):
            return bool(v)
        s = str(v).strip().lower()
        if s in ("1", "true", "yes", "y", "on"):
            return True
        if s in ("0", "false", "no", "n", "off"):
            return False
        return None

    cfg_use_include = _bool_or_none(cfg_filters.get("use_include"))
    cfg_use_exclude = _bool_or_none(cfg_filters.get("use_exclude"))

    cfg_include = [str(x) for x in cfg_filters.get("include", [])] if isinstance(cfg_filters.get("include", []), list) else []
    cfg_exclude = [str(x) for x in cfg_filters.get("exclude", [])] if isinstance(cfg_filters.get("exclude", []), list) else []

    def _split_patterns(values: list[str]) -> list[str]:
        out: list[str] = []
        for v in values:
            for part in str(v).split(","):
                s = part.strip()
                if s:
                    out.append(s)
        return out

    cli_include = _split_patterns(list(ns.include or []))
    cli_exclude = _split_patterns(list(ns.exclude or []))

    include_patterns = cli_include if cli_include else cfg_include
    exclude_patterns = cli_exclude if cli_exclude else cfg_exclude

    # CLI overrides cfg; defaults are enabled.
    use_include = ns.use_include if ns.use_include is not None else (cfg_use_include if cfg_use_include is not None else True)
    use_exclude = ns.use_exclude if ns.use_exclude is not None else (cfg_use_exclude if cfg_use_exclude is not None else True)

    def _match_any(name: str, patterns: list[str]) -> bool:
        return any(fnmatch.fnmatchcase(name, pat) for pat in patterns)

    def _should_run(step_name: str) -> bool:
        if use_include and include_patterns and not _match_any(step_name, include_patterns):
            return False
        if use_exclude and exclude_patterns and _match_any(step_name, exclude_patterns):
            return False
        return True

    steps: list[dict[str, Any]] = data.get("step", [])
    steps = [s for s in steps if _should_run(str(s.get("name", "")))]
    if ns.ci:
        steps = [s for s in steps if str(s.get("kind", "")).lower() != "patch"]
    total = len(steps)
    shutil.rmtree(patch_dst, ignore_errors=True)
    patch_dst.mkdir(parents=True, exist_ok=True)

    _banner(
        master_log,
        "BADGUYS SUITE START\n"
        f"repo={REPO_ROOT}\n"
        f"runner={' '.join(runner_argv)}\n"
        f"issue={issue}\n"
        f"dst={patch_dst}\n"
        f"steps={total}\n"
        f"include={include_patterns} (use={use_include})\n"
        f"exclude={exclude_patterns} (use={use_exclude})\n"
        f"verbose={ns.verbose}\n",
    )

    print(f"BADGUYS: steps={total} issue={issue} log={master_log}", flush=True)

    failed = 0

    def _current_branch() -> str:
        p = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO_ROOT)
        return (p.stdout or "").strip() if p.returncode == 0 else ""

    def _force_return_to_main_if_needed(step_name: str) -> None:
        # Only some steps are meant to run off main.
        allow_non_main = {
            "branch_create_tmp",
            "run_patch_on_non_main_should_fail",
            "allow_non_main_with_--allow-non-main",
            "return_to_main",
        }
        if step_name in allow_non_main:
            return
        br = _current_branch()
        if br and br != "main":
            _run(["git", "checkout", "main"], cwd=REPO_ROOT)
        # Best-effort delete of the tmp branch.
        _run(["git", "branch", "-D", tmp_branch], cwd=REPO_ROOT)

    for idx, step in enumerate(steps, start=1):
        name = str(step.get("name", f"step_{idx:02d}"))
        _force_return_to_main_if_needed(name)
        kind = str(step.get("kind", "patch"))
        exp = _expect(step.get("expect", {}))
        flags = [str(x) for x in step.get("runner_flags", [])]
        script_rel = step.get("script")

        wsp = _ws_policy(suite_ws, step.get("workspace"))
        if wsp.clean_before:
            _clean_workspace(issue)

        if name == "seed_latest_failure":
            unsuccessful = REPO_ROOT / "patches" / "unsuccessful"
            if unsuccessful.exists():
                for p in unsuccessful.glob(f"issue_{issue}_*.py"):
                    p.unlink()


        _banner(master_log, f"STEP {idx:02d}: {name} (kind={kind})")

        step_log = REPO_ROOT / "patches" / "badguys_step_logs" / f"{idx:02d}_{_safe_name(name)}.log"
        # Clear step log for this run
        if step_log.exists():
            step_log.unlink()

        status = "ok"
        if kind == "shell":
            cmd_s = str(step.get("cmd", ""))
            _append(master_log, f"CMD: {cmd_s}\n")
            p = _run(["bash", "-lc", cmd_s], cwd=REPO_ROOT)
            _append(master_log, p.stdout + p.stderr)
            _append(step_log, p.stdout + p.stderr)

            ok = (p.returncode == 0)
            if ok != exp.ok:
                failed += 1
                status = "failed"
                _append(master_log, f"FAIL: expected ok={exp.ok} got rc={p.returncode}\n")
            if ns.verbose:
                _append(master_log, f"rc={p.returncode}\n")
            print(_fmt_progress(idx, total, name, status), flush=True)
            if wsp.clean_after:
                _clean_workspace(issue)
            continue

        if not script_rel:
            failed += 1
            status = "failed"
            _append(master_log, "ERROR: missing script\n")
            print(_fmt_progress(idx, total, name, status), flush=True)
            if wsp.clean_after:
                _clean_workspace(issue)
            continue

        src = (REPO_ROOT / "badguys" / str(script_rel)).resolve()
        if not src.exists():
            failed += 1
            status = "failed"
            _append(master_log, f"ERROR: missing script: {src}\n")
            print(_fmt_progress(idx, total, name, status), flush=True)
            if wsp.clean_after:
                _clean_workspace(issue)
            continue

        if kind == "patch":
            # For -l/--rerun-latest tests, the runner expects archived scripts named "issue_<id>.py".
            # Use that canonical name only for the seed_latest_failure patch; use prefixed names for others.
            if src.name.startswith("00_seed_latest_failure"):
                dst = patch_dst / f"issue_{issue}.py"
            else:
                dst = patch_dst / f"issue_{issue}_{src.name}"
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            patch_path = dst
        elif kind == "reject":
            patch_path = src
        else:
            failed += 1
            status = "failed"
            _append(master_log, f"ERROR: unknown kind={kind}\n")
            print(_fmt_progress(idx, total, name, status), flush=True)
            if wsp.clean_after:
                _clean_workspace(issue)
            continue

        message = f"badguys:{name}"
        cmd = [*runner_argv, *flags, issue, message, str(patch_path)]

        _append(master_log, "CMD: " + " ".join(shlex.quote(c) for c in cmd) + "\n\n")
        p = _run(cmd, cwd=REPO_ROOT)
        _append(master_log, p.stdout + p.stderr)
        _append(step_log, p.stdout + p.stderr)

        am_log = REPO_ROOT / "patches" / "am_patch.log"
        tail = _tail(am_log)
        if tail:
            _append(master_log, "\n---- tail(patches/am_patch.log) ----\n")
            _append(master_log, tail)
            _append(master_log, "---- end tail ----\n\n")
            _append(step_log, "\n---- tail(patches/am_patch.log) ----\n")
            _append(step_log, tail)
            _append(step_log, "---- end tail ----\n")

        ok = (p.returncode == 0)
        if exp.ok:
            if not ok:
                failed += 1
                status = "failed"
                _append(master_log, f"FAIL: expected ok=True got rc={p.returncode}\n")
        else:
            if ok:
                failed += 1
                status = "failed"
                _append(master_log, "FAIL: expected failure got rc=0\n")
            else:
                st, cat = _parse_fingerprint(tail)
                if (exp.stage or exp.category) and (st is None and cat is None):
                    failed += 1
                    status = "failed"
                    _append(master_log, "FAIL: missing fingerprint in patches/am_patch.log tail\n")
                if exp.stage and st != exp.stage:
                    failed += 1
                    status = "failed"
                    _append(master_log, f"FAIL: expected stage={exp.stage} got {st}\n")
                if exp.category and cat != exp.category:
                    failed += 1
                    status = "failed"
                    _append(master_log, f"FAIL: expected category={exp.category} got {cat}\n")

        if ns.verbose:
            _append(master_log, f"rc={p.returncode}\n")
        print(_fmt_progress(idx, total, name, status), flush=True)

        if wsp.clean_after:
            _clean_workspace(issue)

    # Clean patch staging directory (unless explicitly requested to keep)
    if not ns.keep_workspace:
        if failed == 0 or not ns.keep_workspace_on_fail:
            shutil.rmtree(patch_dst, ignore_errors=True)

    # Delete any archived patch scripts created by this suite run.
    # (Keeps the repo patches archive tidy; these are test artifacts.)
    if succ_dir.exists():
        for p in succ_dir.glob("*.py"):
            if p.resolve() not in _succ_before:
                p.unlink()
    if unsucc_dir.exists():
        for p in unsucc_dir.glob("*.py"):
            if p.resolve() not in _unsucc_before:
                p.unlink()

    # Delete any runner logs created by this suite run (patches/logs/*).
    if logs_dir.exists():
        for p in logs_dir.glob("*"):
            try:
                if p.resolve() not in _logs_before:
                    p.unlink()
            except FileNotFoundError:
                pass

    # Ensure we leave the repo on main and drop the tmp branch.
    _run(["git", "checkout", "main"], cwd=REPO_ROOT)
    _run(["git", "branch", "-D", tmp_branch], cwd=REPO_ROOT)

    # final cleanup (unless explicitly requested to keep)
    if not ns.keep_workspace:
        if failed == 0 or not ns.keep_workspace_on_fail:
            _clean_workspace(issue)

    _banner(master_log, f"BADGUYS SUITE END\nfailed={failed}")
    print(f"BADGUYS: done failed={failed} log={master_log}", flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
