#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import glob
import shutil
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import tomllib


@dataclass(frozen=True)
class SuiteCfg:
    repo_root: Path
    config_path: str
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
    per_run_logs_post_run: str

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
    runner_ipc_artifacts: dict[str, dict[str, Path]]

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
    cli_per_run_logs_post_run: Optional[str],
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

    # Deterministic IPC socket naming for runner result detection.
    runner_cmd = runner_cmd + [
        "--ipc-socket-mode=patch_dir",
        "--ipc-socket-name-template=am_patch_ipc_{issue}.sock",
    ]

    # BadGuys console verbosity (short flags override this).
    console_verbosity = _resolve_value(cli_console_verbosity, suite.get("console_verbosity"), "normal").strip()
    if console_verbosity not in {"debug", "verbose", "normal", "quiet"}:
        raise SystemExit(f"FAIL: invalid BadGuys console verbosity: {console_verbosity!r}")

    # BadGuys log verbosity (controls central + per-test logs).
    log_verbosity = _resolve_value(cli_log_verbosity, suite.get("log_verbosity"), "normal").strip()
    if log_verbosity not in {"debug", "verbose", "normal", "quiet"}:
        raise SystemExit(f"FAIL: invalid BadGuys log verbosity: {log_verbosity!r}")

    per_run_logs_post_run = _resolve_value(
        cli_per_run_logs_post_run,
        suite.get("per_run_logs_post_run"),
        "keep_all",
    ).strip()
    if per_run_logs_post_run not in {"delete_all", "keep_all", "delete_successful"}:
        raise SystemExit(
            f"FAIL: invalid per_run_logs_post_run: {per_run_logs_post_run!r} (expected delete_all|keep_all|delete_successful)"
        )

    patches_dir = repo_root / str(suite.get("patches_dir", "patches"))
    logs_dir = repo_root / str(suite.get("logs_dir", "patches/badguys_logs"))
    central_log_pattern = str(suite.get("central_log_pattern", "patches/badguys_{run_id}.log"))

    lock_path = repo_root / str(lock.get("path", "patches/badguys.lock"))
    lock_ttl_seconds = int(lock.get("ttl_seconds", 3600))
    lock_on_conflict = str(lock.get("on_conflict", "fail"))

    return SuiteCfg(
        repo_root=repo_root,
        config_path=str(config_path),
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
        per_run_logs_post_run=per_run_logs_post_run,
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


def _post_run_cleanup_logs(cfg: SuiteCfg, per_test_ok: dict[str, bool]) -> None:
    mode = cfg.per_run_logs_post_run
    logs_dir = cfg.logs_dir
    if mode == "keep_all":
        return
    if mode == "delete_all":
        if logs_dir.exists():
            shutil.rmtree(logs_dir)
        return
    # delete_successful
    for test_name, ok in per_test_ok.items():
        if not ok:
            continue
        p = logs_dir / f"{test_name}.log"
        try:
            p.unlink()
        except FileNotFoundError:
            pass


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


def _run_cmd_with_heartbeat(ctx: Ctx, *, test_name: str, argv: list[str], cwd: Path) -> CmdOutcome:
    started = time.monotonic()
    last_msg: Optional[str] = None
    hb_interval = 5.0

    ipc_holder: dict[str, dict | None] = {"result": None}
    ipc_thread: threading.Thread | None = None
    socket_path: Path | None = None
    if _is_runner_cmd(ctx.cfg, argv):
        from badguys.ipc_result_reader import read_ipc_result_tee

        socket_path = ctx.cfg.patches_dir / f"am_patch_ipc_{ctx.cfg.issue_id}.sock"
        trace_path = ctx.cfg.logs_dir / test_name / "runner_ipc.jsonl"
        trace_path.parent.mkdir(parents=True, exist_ok=True)


        def _run_reader() -> None:
            ipc_holder["result"] = read_ipc_result_tee(
                socket_path,
                connect_timeout_s=3.0,
                total_timeout_s=0.0,
                trace_path=trace_path,
            )

        ipc_thread = threading.Thread(target=_run_reader, name="badguys_ipc_reader", daemon=True)
        ipc_thread.start()

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
            except KeyboardInterrupt:
                # Ensure the child process does not leak when the user aborts the suite.
                try:
                    if proc.poll() is None:
                        proc.terminate()
                        try:
                            proc.wait(timeout=2.0)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                except Exception:
                    # Best-effort cleanup; the interrupt should still propagate.
                    pass
                raise
    finally:
        _clear_heartbeat(ctx, last_msg)

    if ipc_thread is not None:
        ipc_thread.join(timeout=0.25)

    ipc_result = ipc_holder["result"]
    if ipc_result is not None:
        try:
            rc = int(ipc_result["return_code"])
        except Exception:
            pass

        artifacts: dict[str, Path] = {}
        log_path = ipc_result.get("log_path")
        json_path = ipc_result.get("json_path")
        if isinstance(log_path, str) and log_path:
            artifacts["log_path"] = Path(log_path)
        if isinstance(json_path, str) and json_path:
            artifacts["json_path"] = Path(json_path)
        if artifacts:
            ctx.runner_ipc_artifacts[test_name] = artifacts

    cp = subprocess.CompletedProcess(args=argv, returncode=int(rc), stdout=stdout, stderr=stderr)
    return CmdOutcome(cp=cp, ipc_result=ipc_result)


def _is_runner_cmd(cfg: SuiteCfg, argv: list[str]) -> bool:
    if not argv:
        return False
    if len(argv) < len(cfg.runner_cmd):
        return False
    return argv[: len(cfg.runner_cmd)] == cfg.runner_cmd


@dataclass(frozen=True)
class CmdOutcome:
    cp: subprocess.CompletedProcess[str]
    ipc_result: dict | None
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
    if test_name is not None:
        artifacts = ctx.runner_ipc_artifacts.pop(test_name, None)
        if artifacts:
            dst_dir = ctx.cfg.logs_dir / test_name
            dst_dir.mkdir(parents=True, exist_ok=True)

            src_log = artifacts.get("log_path")
            if src_log is not None and src_log.exists():
                shutil.copy2(src_log, dst_dir / "runner.log")

            src_json = artifacts.get("json_path")
            if src_json is not None and src_json.exists():
                shutil.copy2(src_json, dst_dir / "runner.jsonl")

    # Contract: after EACH test, the engine must delete:
    # - patches/workspaces/issue_666/
    # - patches/logs/issue_666*
    # - patches/successful/issue_666*
    # - patches/unsuccessful/issue_666*
    repo_root = ctx.repo_root
    ws = repo_root / "patches" / "workspaces" / f"issue_{issue_id}"
    _action(ctx, test_name=test_name, kind="CLEANUP", phase="DO", msg=f"rm -rf {ws}")
    shutil.rmtree(ws, ignore_errors=True)
    _action(ctx, test_name=test_name, kind="CLEANUP", phase="OK", msg=f"rm -rf {ws}")

    logs_dir = repo_root / "patches" / "logs"
    issue_logs_pat = f"issue_{issue_id}*"
    _action(ctx, test_name=test_name, kind="CLEANUP", phase="DO", msg=f"rm {logs_dir}/{issue_logs_pat}")
    if logs_dir.exists():
        for p in logs_dir.glob(issue_logs_pat):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                try:
                    p.unlink()
                except FileNotFoundError:
                    pass

    _action(ctx, test_name=test_name, kind="CLEANUP", phase="OK", msg=f"rm {logs_dir}/{issue_logs_pat}")

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


def _load_eval_rules(repo_root: Path, config_path: Path) -> dict:
    raw = tomllib.loads((repo_root / config_path).read_text(encoding="utf-8"))
    return raw.get("evaluation", {})


def _rules_for_step(evaluation: dict, *, test_id: str, step_index: int) -> dict:
    tests = evaluation.get("tests", {})
    if not isinstance(tests, dict):
        return {}
    t = tests.get(test_id, {})
    if not isinstance(t, dict):
        return {}
    steps = t.get("steps", {})
    if not isinstance(steps, dict):
        return {}
    s = steps.get(str(step_index)) if str(step_index) in steps else steps.get(step_index)
    if not isinstance(s, dict):
        return {}
    return s


def _run_test_plan(test, ctx: Ctx) -> bool:
    from badguys.bdg_executor import execute_bdg
    from badguys.bdg_evaluator import StepResult, evaluate_step
    from badguys.bdg_loader import BdgTest
    from badguys.bdg_materializer import materialize_assets

    name = getattr(test, "name", "(unknown)")
    evaluation = _load_eval_rules(ctx.repo_root, Path(ctx.cfg.config_path))
    strict = bool(evaluation.get("strict_coverage", True))

    try:
        obj = test.run(ctx)
    except SystemExit as e:
        _emit(ctx, level="verbose", test_name=name, text=f"FAIL: {e}\n")
        _emit(ctx, level="verbose", test_name=name, text=f"TEST END {name} FAIL\n")
        return False

    if isinstance(obj, BdgTest):
        bdg = obj
        mats = materialize_assets(repo_root=ctx.repo_root, issue_id=ctx.cfg.issue_id, bdg=bdg)
        _emit(ctx, level="verbose", test_name=name, text=f"TEST BEGIN {name}\n")

        step_results = execute_bdg(
            repo_root=ctx.repo_root,
            cfg_runner_cmd=list(ctx.cfg.runner_cmd),
            issue_id=ctx.cfg.issue_id,
            bdg=bdg,
            mats=mats,
        )

        ok = True
        prior: dict[int, StepResult] = {}
        for idx, r in enumerate(step_results):
            rules = _rules_for_step(evaluation, test_id=bdg.test_id, step_index=idx)
            if strict and not rules:
                ok = False
                _emit(ctx, level="verbose", test_name=name, text=f"FAIL: missing evaluation rules for step {idx}\n")
            else:
                passed, msg = evaluate_step(
                    rules=rules,
                    result=r,
                    prior=prior,
                    test_id=bdg.test_id,
                    step_index=idx,
                )
                if not passed:
                    ok = False
                    _emit(ctx, level="verbose", test_name=name, text=f"FAIL: step {idx}: {msg}\n")
            # Emit step output into per-run log for parity with legacy CmdStep/FuncStep tests.
            if r.stdout:
                _emit(ctx, level="verbose", test_name=name, text=r.stdout)
                if not r.stdout.endswith("\n"):
                    _emit(ctx, level="verbose", test_name=name, text="\n")
            if r.stderr:
                _emit(ctx, level="verbose", test_name=name, text=r.stderr)
                if not r.stderr.endswith("\n"):
                    _emit(ctx, level="verbose", test_name=name, text="\n")
            # For RUN_RUNNER steps, also emit the resolved runner log path as 'LOG: <path>'.
            if bdg.steps[idx].op == "RUN_RUNNER":
                log_link = ctx.cfg.patches_dir / "am_patch.log"
                try:
                    resolved = log_link.resolve(strict=True)
                except FileNotFoundError:
                    resolved = None
                if resolved is not None:
                    _emit(ctx, level="verbose", test_name=name, text=f"LOG: {resolved}\n")

            prior[idx] = r

        _emit(ctx, level="verbose", test_name=name, text=f"TEST END {name} {'PASS' if ok else 'FAIL'}\n")
        return ok

    raise SystemExit(f"FAIL: test {name} returned unsupported type: {type(obj).__name__}")

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
    ap.add_argument(
        "--per-run-logs-post-run",
        default=None,
        choices=["delete_all", "keep_all", "delete_successful"],
        help="Post-run per-test log cleanup policy",
    )
    ap.add_argument("--include", action="append", default=[], help="Run only named tests (repeatable)")
    ap.add_argument("--exclude", action="append", default=[], help="Skip named tests (repeatable)")
    ap.add_argument("--list-tests", action="store_true", help="List discovered tests and exit")
    args = ap.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    _ensure_repo_root_in_syspath(repo_root)

    cfg = _make_cfg(
        repo_root,
        Path(args.config),
        args.runner_verbosity,
        args.console_verbosity,
        args.log_verbosity,
        args.per_run_logs_post_run,
    )
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
            runner_ipc_artifacts={},
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
                    f"debug: per_run_logs_post_run={cfg.per_run_logs_post_run}\n"
                ),
            )

        commit_limit = int(getattr(tests, "commit_limit", 1))
        commit_tests = [t for t in tests if bool(getattr(t, "makes_commit", False))]
        if len(commit_tests) > commit_limit:
            fail_commit_limit(central_log, commit_limit, commit_tests)

        ok_all = True
        interrupted = False
        per_test_ok: dict[str, bool] = {}
        for idx, t in enumerate(tests):
            try:
                # Enforce deterministic isolation contract.
                _cleanup_issue_artifacts(ctx, issue_id=cfg.issue_id, test_name=getattr(t, "name", None))
    
                ok = False
                try:
                    ok = _run_test_plan(t, ctx)
                finally:
                    _cleanup_issue_artifacts(ctx, issue_id=cfg.issue_id, test_name=getattr(t, "name", None))
    
                per_test_ok[t.name] = bool(ok)

                if ctx.console_verbosity in {"normal", "verbose", "debug"} or ctx.log_verbosity in {"normal", "verbose", "debug"}:
                    _emit(ctx, level="normal", test_name=t.name, text=format_result_line(t.name, ok))
                if not ok:
                    ok_all = False
                    if idx == 0 and bool(getattr(tests, "abort_on_guard_fail", False)):
                        break
    
            except KeyboardInterrupt:
                interrupted = True
                ok_all = False
                _emit(ctx, level="quiet", test_name=None, text="BadGuys interrupted (Ctrl+C)\n")
                break
        # Summary is minimal by contract in quiet, and includes counts in normal+.
        status = "OK" if ok_all else "FAIL"
        passed = sum(1 for ok in per_test_ok.values() if ok)
        failed = sum(1 for ok in per_test_ok.values() if not ok)
        if ctx.console_verbosity == "quiet":
            summary = f"BadGuys summary: {status}\n"
        else:
            summary = f"BadGuys summary: {status} passed={passed} failed={failed}\n"
        _emit(ctx, level="quiet", test_name=None, text=summary)

        _post_run_cleanup_logs(cfg, per_test_ok)

        if interrupted:
            return 130
        return 0 if ok_all else 1
    finally:
        release_lock(repo_root)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
