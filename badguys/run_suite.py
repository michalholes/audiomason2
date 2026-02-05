#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import glob
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import tomllib


@dataclass(frozen=True)
class SuiteCfg:
    repo_root: Path
    issue_id: str
    runner_cmd: list[str]
    patches_dir: Path
    logs_dir: Path
    central_log_pattern: str
    lock_path: Path
    lock_ttl_seconds: int
    lock_on_conflict: str
    console_verbosity: str
    log_verbosity: str

    def central_log_path(self, run_id: str) -> Path:
        rel = self.central_log_pattern.format(run_id=run_id)
        return self.repo_root / Path(rel)


@dataclass
class Ctx:
    repo_root: Path
    run_id: str
    central_log: Path
    cfg: SuiteCfg
    console_verbosity: str
    log_verbosity: str

    def step_log_path(self, test_name: str) -> Path:
        # Per-test log name must be stable (no timestamp in filename).
        return self.cfg.logs_dir / f"{test_name}.log"


def _load_config(repo_root: Path, config_path: Path) -> dict:
    p = repo_root / config_path
    if not p.exists():
        return {}
    return tomllib.loads(p.read_text(encoding="utf-8"))


def _resolve_value(cli: Optional[str], cfg_val: Optional[str], default: str) -> str:
    if cli is not None:
        return str(cli)
    if cfg_val is not None:
        return str(cfg_val)
    return default


def _make_cfg(
    repo_root: Path,
    config_path: Path,
    cli_runner_verbosity: Optional[str],
    cli_console_verbosity: Optional[str],
    cli_log_verbosity: Optional[str],
) -> SuiteCfg:
    raw = _load_config(repo_root, config_path)
    suite = raw.get("suite", {})
    lock = raw.get("lock", {})

    issue_id = str(suite.get("issue_id", "666"))
    runner_cmd = [str(x) for x in suite.get("runner_cmd", ["python3", "scripts/am_patch.py"])]

    # When BadGuys is invoked as an am_patch gate, the runner may be executing inside a
    # venv that is not present inside a workspace/clone repo. Allow am_patch to override
    # the Python executable used for nested runner invocations.
    env_py = os.environ.get("AM_PATCH_BADGUYS_RUNNER_PYTHON")
    if env_py and runner_cmd:
        head = str(runner_cmd[0])
        if head in {"python", "python3", "/usr/bin/python3", "/usr/bin/python"} or head.endswith("/python3") or head.endswith("/python"):
            runner_cmd[0] = str(env_py)

    # Runner verbosity (passed through to am_patch via --verbosity=<mode>)
    runner_verbosity = _resolve_value(cli_runner_verbosity, suite.get("runner_verbosity"), "quiet").strip()
    if runner_verbosity:
        runner_cmd = runner_cmd + [f"--verbosity={runner_verbosity}"]

    # BadGuys console verbosity (short flags override this).
    console_verbosity = _resolve_value(cli_console_verbosity, suite.get("console_verbosity"), "normal").strip()
    if console_verbosity not in {"debug", "verbose", "normal", "quiet"}:
        raise SystemExit(f"FAIL: invalid BadGuys console verbosity: {console_verbosity!r}")

    # BadGuys log verbosity (controls central + per-test logs).
    log_verbosity = _resolve_value(cli_log_verbosity, suite.get("log_verbosity"), "normal").strip()
    if log_verbosity not in {"debug", "verbose", "normal", "quiet"}:
        raise SystemExit(f"FAIL: invalid BadGuys log verbosity: {log_verbosity!r}")

    patches_dir = repo_root / str(suite.get("patches_dir", "patches"))
    logs_dir = repo_root / str(suite.get("logs_dir", "patches/badguys_logs"))
    central_log_pattern = str(suite.get("central_log_pattern", "patches/badguys_{run_id}.log"))

    lock_path = repo_root / str(lock.get("path", "patches/badguys.lock"))
    lock_ttl_seconds = int(lock.get("ttl_seconds", 3600))
    lock_on_conflict = str(lock.get("on_conflict", "fail"))

    return SuiteCfg(
        repo_root=repo_root,
        issue_id=issue_id,
        runner_cmd=runner_cmd,
        patches_dir=patches_dir,
        logs_dir=logs_dir,
        central_log_pattern=central_log_pattern,
        lock_path=lock_path,
        lock_ttl_seconds=lock_ttl_seconds,
        lock_on_conflict=lock_on_conflict,
        console_verbosity=console_verbosity,
        log_verbosity=log_verbosity,
    )


_VERBOSITY_ORDER = {"quiet": 0, "normal": 1, "verbose": 2, "debug": 3}


def _want(verbosity: str, level: str) -> bool:
    """Return True if an event at 'level' should be emitted under 'verbosity'."""
    return _VERBOSITY_ORDER[verbosity] >= _VERBOSITY_ORDER[level]


def _ensure_repo_root_in_syspath(repo_root: Path) -> None:
    s = str(repo_root)
    if sys.path and sys.path[0] == s:
        return
    if s not in sys.path:
        sys.path.insert(0, s)


def _init_logs(cfg: SuiteCfg, run_id: str) -> Path:
    logs_dir = cfg.logs_dir
    if logs_dir.exists():
        shutil.rmtree(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    central = cfg.central_log_path(run_id)
    central.parent.mkdir(parents=True, exist_ok=True)
    central.write_text(f"BadGuys run_id={run_id}\n", encoding="utf-8")
    return central


def _emit(ctx: Ctx, *, level: str, test_name: Optional[str], text: str) -> None:
    """Emit a single formatted line to central log, per-test log, and/or console."""
    if _want(ctx.log_verbosity, level):
        ctx.central_log.parent.mkdir(parents=True, exist_ok=True)
        with ctx.central_log.open("a", encoding="utf-8") as f:
            f.write(text)

        if test_name is not None:
            p = ctx.step_log_path(test_name)
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                f.write(text)

    if _want(ctx.console_verbosity, level):
        sys.stdout.write(text)
        sys.stdout.flush()




def _want_heartbeat(ctx: Ctx) -> bool:
    # Heartbeat is console-only and must be disabled in quiet.
    return ctx.console_verbosity in {"normal", "verbose", "debug"}


def _emit_heartbeat(ctx: Ctx, *, test_name: str, started: float, last_msg: Optional[str]) -> str:
    elapsed = int(time.monotonic() - started)
    mm, ss = divmod(elapsed, 60)
    msg = f"STATUS: BadGuys {test_name}  ELAPSED: {mm:02d}:{ss:02d}"
    out = msg
    # Overwrite in TTY, otherwise emit standalone heartbeat lines.
    if sys.stderr.isatty():
        pad = ""
        if last_msg is not None and len(last_msg) > len(msg):
            pad = " " * (len(last_msg) - len(msg))
        sys.stderr.write("\r" + msg + pad)
        sys.stderr.flush()
    else:
        sys.stderr.write("HEARTBEAT: " + msg + "\n")
        sys.stderr.flush()
    return out


def _clear_heartbeat(ctx: Ctx, last_msg: Optional[str]) -> None:
    if not sys.stderr.isatty():
        return
    if last_msg is None:
        return
    sys.stderr.write("\r" + (" " * len(last_msg)) + "\r")
    sys.stderr.flush()


def _run_cmd_with_heartbeat(ctx: Ctx, *, test_name: str, argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    started = time.monotonic()
    last_msg: Optional[str] = None
    hb_interval = 5.0

    proc = subprocess.Popen(
        argv,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        while True:
            try:
                stdout, stderr = proc.communicate(timeout=hb_interval)
                rc = proc.returncode
                break
            except subprocess.TimeoutExpired:
                if _want_heartbeat(ctx):
                    last_msg = _emit_heartbeat(ctx, test_name=test_name, started=started, last_msg=last_msg)
                continue
    finally:
        _clear_heartbeat(ctx, last_msg)

    return subprocess.CompletedProcess(args=argv, returncode=int(rc), stdout=stdout, stderr=stderr)
def _log_banner(ctx: Ctx, test_name: str, title: str) -> None:
    _emit(
        ctx,
        level="verbose",
        test_name=test_name,
        text=(
            "\n" + "=" * 78 + "\n" + f"{test_name}: {title}\n" + "=" * 78 + "\n"
        ),
    )


def _action(ctx: Ctx, *, test_name: Optional[str], kind: str, phase: str, msg: str) -> None:
    _emit(ctx, level="verbose", test_name=test_name, text=f"{kind} {phase}: {msg}\n")


def _cleanup_issue_artifacts(ctx: Ctx, *, issue_id: str, test_name: Optional[str]) -> None:
    # Contract: after EACH test, the engine must delete:
    # - patches/workspaces/issue_666/
    # - all logs in patches/logs
    # - patches/successful/issue_666*
    # - patches/unsuccessful/issue_666*
    repo_root = ctx.repo_root
    ws = repo_root / "patches" / "workspaces" / f"issue_{issue_id}"
    _action(ctx, test_name=test_name, kind="CLEANUP", phase="DO", msg=f"rm -rf {ws}")
    shutil.rmtree(ws, ignore_errors=True)
    _action(ctx, test_name=test_name, kind="CLEANUP", phase="OK", msg=f"rm -rf {ws}")

    logs_dir = repo_root / "patches" / "logs"
    _action(ctx, test_name=test_name, kind="CLEANUP", phase="DO", msg=f"clear {logs_dir}/*")
    if logs_dir.exists():
        for p in logs_dir.glob("*"):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                try:
                    p.unlink()
                except FileNotFoundError:
                    pass

    _action(ctx, test_name=test_name, kind="CLEANUP", phase="OK", msg=f"clear {logs_dir}/*")

    for pat in (
        str(repo_root / "patches" / "successful" / f"issue_{issue_id}*"),
        str(repo_root / "patches" / "unsuccessful" / f"issue_{issue_id}*"),
    ):
        _action(ctx, test_name=test_name, kind="CLEANUP", phase="DO", msg=f"rm {pat}")
        for path_str in glob.glob(pat):
            p = Path(path_str)
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                try:
                    p.unlink()
                except FileNotFoundError:
                    pass
        _action(ctx, test_name=test_name, kind="CLEANUP", phase="OK", msg=f"rm {pat}")


def _run_test_plan(test, ctx: Ctx) -> bool:
    from badguys._util import (
        CmdStep,
        ExpectPathExists,
        FuncStep,
        Plan,
    )

    name = getattr(test, "name", "(unknown)")
    plan_obj = test.run(ctx)
    if not isinstance(plan_obj, Plan):
        raise SystemExit(f"FAIL: test {name} returned invalid plan type: {type(plan_obj).__name__}")

    ok = True

    _emit(ctx, level="verbose", test_name=name, text=f"TEST BEGIN {name}\n")

    for step in plan_obj.steps:
        if isinstance(step, CmdStep):
            argv = step.argv
            cwd = step.cwd if step.cwd is not None else ctx.repo_root
            _log_banner(ctx, name, "cmd")
            cp = _run_cmd_with_heartbeat(ctx, test_name=name, argv=list(argv), cwd=cwd)

            # CMD summary is always at least "$ ..." and "rc=..." in verbose+.
            if _want(ctx.log_verbosity, "verbose") or _want(ctx.console_verbosity, "verbose"):
                args = cp.args if isinstance(cp.args, list) else [str(cp.args)]
                _emit(ctx, level="verbose", test_name=name, text="$ " + " ".join(str(a) for a in args) + "\n")
                _emit(ctx, level="verbose", test_name=name, text=f"rc={cp.returncode}\n")

            # In verbose/debug, include stdout/stderr.
            if cp.stdout:
                _emit(ctx, level="verbose", test_name=name, text=cp.stdout.rstrip("\n") + "\n")
            if cp.stderr:
                _emit(ctx, level="verbose", test_name=name, text=cp.stderr.rstrip("\n") + "\n")
            if cp.returncode != step.expect_rc:
                ok = False
                _emit(
                    ctx,
                    level="verbose",
                    test_name=name,
                    text=f"FAIL: returncode={cp.returncode} expected={step.expect_rc}\n",
                )
        elif isinstance(step, ExpectPathExists):
            _log_banner(ctx, name, "expect_path_exists")
            if not step.path.exists():
                ok = False
                _emit(ctx, level="verbose", test_name=name, text=f"FAIL: missing path: {step.path}\n")
            else:
                _emit(ctx, level="verbose", test_name=name, text=f"OK: path exists: {step.path}\n")
        elif isinstance(step, FuncStep):
            _log_banner(ctx, name, f"func: {step.name}")
            try:
                _action(ctx, test_name=name, kind="ACTION", phase="DO", msg=step.name)
                step.fn()
                _action(ctx, test_name=name, kind="ACTION", phase="OK", msg=step.name)
            except Exception:
                ok = False
                tb = traceback.format_exc()
                _action(ctx, test_name=name, kind="ACTION", phase="FAIL", msg=step.name)
                _emit(ctx, level="verbose", test_name=name, text="FAIL: func step raised\n" + tb + "\n")
        else:
            ok = False
            _emit(ctx, level="verbose", test_name=name, text=f"FAIL: unknown step type: {type(step).__name__}\n")

    # Cleanup any per-test temp files provided by the plan.
    for p in plan_obj.cleanup_paths:
        try:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink()
        except FileNotFoundError:
            pass

    _emit(ctx, level="verbose", test_name=name, text=f"TEST END {name} {'PASS' if ok else 'FAIL'}\n")
    return ok


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python3 badguys/badguys.py")
    ap.add_argument("--config", default="badguys/config.toml", help="Config path (repo-relative)")
    ap.add_argument("--commit-limit", type=int, default=None, help="Override commit_limit from config")
    ap.add_argument(
        "--runner-verbosity",
        default=None,
        choices=["debug", "verbose", "normal", "quiet"],
        help="Override runner verbosity (passed as --verbosity=<mode>)",
    )
    vg = ap.add_mutually_exclusive_group()
    vg.add_argument("-q", dest="console_verbosity", action="store_const", const="quiet")
    vg.add_argument("-n", dest="console_verbosity", action="store_const", const="normal")
    vg.add_argument("-v", dest="console_verbosity", action="store_const", const="verbose")
    vg.add_argument("-d", dest="console_verbosity", action="store_const", const="debug")
    ap.add_argument(
        "--log-verbosity",
        default=None,
        choices=["debug", "verbose", "normal", "quiet"],
        help="BadGuys log verbosity (central + per-test logs)",
    )
    ap.add_argument("--include", action="append", default=[], help="Run only named tests (repeatable)")
    ap.add_argument("--exclude", action="append", default=[], help="Skip named tests (repeatable)")
    ap.add_argument("--list-tests", action="store_true", help="List discovered tests and exit")
    args = ap.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    _ensure_repo_root_in_syspath(repo_root)

    cfg = _make_cfg(repo_root, Path(args.config), args.runner_verbosity, args.console_verbosity, args.log_verbosity)
    run_id = time.strftime("%Y%m%d_%H%M%S")

    from badguys.discovery import discover_tests
    from badguys._util import acquire_lock, fail_commit_limit, format_result_line, release_lock

    acquire_lock(
        repo_root,
        path=cfg.lock_path,
        ttl_seconds=cfg.lock_ttl_seconds,
        on_conflict=cfg.lock_on_conflict,
    )

    try:
        central_log = _init_logs(cfg, run_id)

        tests = discover_tests(
            repo_root=repo_root,
            config_path=Path(args.config),
            cli_commit_limit=args.commit_limit,
            cli_include=list(args.include),
            cli_exclude=list(args.exclude),
        )

        if args.list_tests:
            for t in tests:
                print(t.name)
            return 0

        # Debug: log resolved config details
        ctx = Ctx(
            repo_root=repo_root,
            run_id=run_id,
            central_log=central_log,
            cfg=cfg,
            console_verbosity=cfg.console_verbosity,
            log_verbosity=cfg.log_verbosity,
        )
        _emit(ctx, level="quiet", test_name=None, text="BadGuys start\n")

        if ctx.console_verbosity == "debug" or ctx.log_verbosity == "debug":
            _emit(
                ctx,
                level="debug",
                test_name=None,
                text=(
                    f"debug: config_path={args.config}\n"
                    f"debug: console_verbosity={cfg.console_verbosity}\n"
                    f"debug: log_verbosity={cfg.log_verbosity}\n"
                    f"debug: runner_cmd={' '.join(cfg.runner_cmd)}\n"
                    f"debug: issue_id={cfg.issue_id}\n"
                ),
            )

        commit_limit = int(getattr(tests, "commit_limit", 1))
        commit_tests = [t for t in tests if bool(getattr(t, "makes_commit", False))]
        if len(commit_tests) > commit_limit:
            fail_commit_limit(central_log, commit_limit, commit_tests)

        ok_all = True
        for idx, t in enumerate(tests):
            # Enforce deterministic isolation contract.
            _cleanup_issue_artifacts(ctx, issue_id=cfg.issue_id, test_name=getattr(t, "name", None))

            ok = False
            try:
                ok = _run_test_plan(t, ctx)
            finally:
                _cleanup_issue_artifacts(ctx, issue_id=cfg.issue_id, test_name=getattr(t, "name", None))

            if ctx.console_verbosity in {"normal", "verbose", "debug"} or ctx.log_verbosity in {"normal", "verbose", "debug"}:
                _emit(ctx, level="normal", test_name=t.name, text=format_result_line(t.name, ok))
            if not ok:
                ok_all = False
                if idx == 0 and bool(getattr(tests, "abort_on_guard_fail", False)):
                    break

        # Summary for quiet and normal+.
        passed = 0
        failed = 0
        # We don't keep per-test state here; compute from ok_all only.
        # Summary is minimal by contract.
        status = "OK" if ok_all else "FAIL"
        _emit(ctx, level="quiet", test_name=None, text=f"BadGuys summary: {status}\n")

        return 0 if ok_all else 1
    finally:
        release_lock(repo_root)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
