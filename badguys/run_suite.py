#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import shutil
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
    suite_verbosity: str

    def central_log_path(self, run_id: str) -> Path:
        rel = self.central_log_pattern.format(run_id=run_id)
        return self.repo_root / Path(rel)


@dataclass
class Ctx:
    repo_root: Path
    run_id: str
    central_log: Path
    cfg: SuiteCfg
    suite_verbosity: str

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
    cli_suite_verbosity: Optional[str],
) -> SuiteCfg:
    raw = _load_config(repo_root, config_path)
    suite = raw.get("suite", {})
    lock = raw.get("lock", {})

    issue_id = str(suite.get("issue_id", "666"))
    runner_cmd = [str(x) for x in suite.get("runner_cmd", ["python3", "scripts/am_patch.py"])]

    # Runner verbosity (passed through to am_patch via --verbosity=<mode>)
    runner_verbosity = _resolve_value(cli_runner_verbosity, suite.get("runner_verbosity"), "quiet").strip()
    if runner_verbosity:
        runner_cmd = runner_cmd + [f"--verbosity={runner_verbosity}"]

    # Badguys suite verbosity (controls console output; logs are always complete)
    suite_verbosity = _resolve_value(cli_suite_verbosity, suite.get("verbosity"), "normal").strip()
    if suite_verbosity not in {"debug", "verbose", "normal", "quiet"}:
        raise SystemExit(f"FAIL: invalid suite verbosity: {suite_verbosity!r}")

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
        suite_verbosity=suite_verbosity,
    )


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
    central.write_text(f"badguys run_id={run_id}\n", encoding="utf-8")
    return central


def _log_to_files(ctx: Ctx, *, test_name: Optional[str], text: str) -> None:
    # Always append to central log.
    ctx.central_log.parent.mkdir(parents=True, exist_ok=True)
    with ctx.central_log.open("a", encoding="utf-8") as f:
        f.write(text)

    # Also append to per-test log if a test is active.
    if test_name is not None:
        p = ctx.step_log_path(test_name)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(text)

    # Console mirroring based on suite verbosity.
    if ctx.suite_verbosity in {"verbose", "debug"}:
        sys.stdout.write(text)
        sys.stdout.flush()


def _log_banner(ctx: Ctx, test_name: str, title: str) -> None:
    _log_to_files(
        ctx,
        test_name=test_name,
        text=(
            "\n" + "=" * 78 + "\n" + f"{test_name}: {title}\n" + "=" * 78 + "\n"
        ),
    )


def _cleanup_issue_artifacts(repo_root: Path, issue_id: str) -> None:
    # Contract: after EACH test, the engine must delete:
    # - patches/workspaces/issue_666/
    # - all logs in patches/logs
    # - patches/successful/issue_666*
    # - patches/unsuccessful/issue_666*
    ws = repo_root / "patches" / "workspaces" / f"issue_{issue_id}"
    shutil.rmtree(ws, ignore_errors=True)

    logs_dir = repo_root / "patches" / "logs"
    if logs_dir.exists():
        for p in logs_dir.glob("*"):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                try:
                    p.unlink()
                except FileNotFoundError:
                    pass

    for pat in (
        str(repo_root / "patches" / "successful" / f"issue_{issue_id}*"),
        str(repo_root / "patches" / "unsuccessful" / f"issue_{issue_id}*"),
    ):
        for path_str in glob.glob(pat):
            p = Path(path_str)
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                try:
                    p.unlink()
                except FileNotFoundError:
                    pass


def _run_test_plan(test, ctx: Ctx) -> bool:
    from badguys._util import (
        CmdStep,
        ExpectPathExists,
        FuncStep,
        Plan,
        _format_completed_process,
        _run_cmd,
    )

    name = getattr(test, "name", "(unknown)")
    plan_obj = test.run(ctx)
    if not isinstance(plan_obj, Plan):
        raise SystemExit(f"FAIL: test {name} returned invalid plan type: {type(plan_obj).__name__}")

    ok = True

    for step in plan_obj.steps:
        if isinstance(step, CmdStep):
            argv = step.argv
            cwd = step.cwd if step.cwd is not None else ctx.repo_root
            _log_banner(ctx, name, "cmd")
            cp = _run_cmd(argv, cwd=cwd)
            _log_to_files(ctx, test_name=name, text=_format_completed_process(cp))
            if cp.returncode != step.expect_rc:
                ok = False
                _log_to_files(
                    ctx,
                    test_name=name,
                    text=f"FAIL: returncode={cp.returncode} expected={step.expect_rc}\n",
                )
        elif isinstance(step, ExpectPathExists):
            _log_banner(ctx, name, "expect_path_exists")
            if not step.path.exists():
                ok = False
                _log_to_files(ctx, test_name=name, text=f"FAIL: missing path: {step.path}\n")
            else:
                _log_to_files(ctx, test_name=name, text=f"OK: path exists: {step.path}\n")
        elif isinstance(step, FuncStep):
            _log_banner(ctx, name, f"func: {step.name}")
            try:
                step.fn()
                _log_to_files(ctx, test_name=name, text="OK: func step completed\n")
            except Exception:
                ok = False
                tb = traceback.format_exc()
                _log_to_files(ctx, test_name=name, text="FAIL: func step raised\n" + tb + "\n")
        else:
            ok = False
            _log_to_files(ctx, test_name=name, text=f"FAIL: unknown step type: {type(step).__name__}\n")

    # Cleanup any per-test temp files provided by the plan.
    for p in plan_obj.cleanup_paths:
        try:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink()
        except FileNotFoundError:
            pass

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
    ap.add_argument(
        "--verbosity",
        default=None,
        choices=["debug", "verbose", "normal", "quiet"],
        help="Badguys suite verbosity (CLI overrides cfg; cfg overrides defaults)",
    )
    ap.add_argument("--include", action="append", default=[], help="Run only named tests (repeatable)")
    ap.add_argument("--exclude", action="append", default=[], help="Skip named tests (repeatable)")
    ap.add_argument("--list-tests", action="store_true", help="List discovered tests and exit")
    args = ap.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    _ensure_repo_root_in_syspath(repo_root)

    cfg = _make_cfg(repo_root, Path(args.config), args.runner_verbosity, args.verbosity)
    run_id = time.strftime("%Y%m%d_%H%M%S")

    from badguys.tests import discover_tests
    from badguys._util import acquire_lock, fail_commit_limit, print_result, release_lock

    acquire_lock(
        repo_root,
        path=cfg.lock_path,
        ttl_seconds=cfg.lock_ttl_seconds,
        on_conflict=cfg.lock_on_conflict,
    )

    if cfg.suite_verbosity == "quiet":
        print(f"badguys: running tests (count=unknown) ...")

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
            suite_verbosity=cfg.suite_verbosity,
        )
        if ctx.suite_verbosity == "debug":
            _log_to_files(
                ctx,
                test_name=None,
                text=(
                    f"debug: config_path={args.config}\n"
                    f"debug: suite_verbosity={cfg.suite_verbosity}\n"
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
            _cleanup_issue_artifacts(repo_root, cfg.issue_id)

            ok = False
            try:
                ok = _run_test_plan(t, ctx)
            finally:
                _cleanup_issue_artifacts(repo_root, cfg.issue_id)

            if ctx.suite_verbosity == "normal":
                print_result(t.name, ok)
            if not ok:
                ok_all = False
                if idx == 0 and bool(getattr(tests, "abort_on_guard_fail", False)):
                    break

        if ctx.suite_verbosity == "quiet":
            status = "OK" if ok_all else "FAIL"
            print(f"badguys: suite result: {status}")

        return 0 if ok_all else 1
    finally:
        release_lock(repo_root)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
