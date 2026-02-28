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
from dataclasses import dataclass, replace
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
    per_run_logs_post_run: str

    def central_log_path(self, run_id: str) -> Path:
        rel = self.central_log_pattern.format(run_id=run_id)
        return self.repo_root / Path(rel)


@dataclass
class Ctx:
    repo_root: Path
    live_repo_root: Path
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



def _is_am_patch_runner_argv(argv: list[str]) -> bool:
    # Detect nested am_patch runner invocations launched by BadGuys tests.
    # Deterministic: purely based on argv content.
    for a in argv:
        if a == "scripts/am_patch.py" or a.endswith("/scripts/am_patch.py"):
            return True
    return False


def _run_git(argv: list[str], *, cwd: Path) -> None:
    cp = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True)
    if cp.returncode != 0:
        msg = (cp.stdout or "").rstrip("\n") + "\n" + (cp.stderr or "").rstrip("\n")
        raise SystemExit(f"FAIL: git command failed: {' '.join(argv)}\n{msg}")


def _prepare_hermetic_live_repo(repo_root: Path) -> Path:
    # BadGuys is often executed in environments where the checkout has no .git (e.g. source exports).
    # Many runner flows require a git working tree. Create a hermetic git repo copy for runner invocations.
    live_repo = repo_root / ".badguys_live_repo"
    shutil.rmtree(live_repo, ignore_errors=True)

    def _ignore(dirpath: str, names: list[str]) -> set[str]:
        ignore: set[str] = set()
        base = os.path.basename(dirpath)
        # Global ignores
        for n in names:
            if n in {
                ".git",
                "patches",
                ".badguys_live_repo",
                "__pycache__",
                ".pytest_cache",
                ".mypy_cache",
                ".ruff_cache",
                ".tox",
                "node_modules",
            }:
                ignore.add(n)
        return ignore

    shutil.copytree(repo_root, live_repo, symlinks=True, ignore=_ignore)

    # Safety reset: if a .git directory is present for any reason, remove it before git init.
    git_dir = live_repo / ".git"
    if git_dir.exists() or git_dir.is_symlink():
        if git_dir.is_dir() and not git_dir.is_symlink():
            shutil.rmtree(git_dir)
        else:
            git_dir.unlink()

    # Hermetic patches directory.
    #
    # BadGuys runs the am_patch runner inside the hermetic repo. The runner relies on
    # Path.relative_to() in a few places, and mixing symlink paths with resolved real
    # paths can raise ValueError. Keep patches/ as a real directory inside the hermetic
    # repo to avoid symlink prefix mismatches.
    patches_dir = live_repo / "patches"
    if patches_dir.exists() or patches_dir.is_symlink():
        if patches_dir.is_symlink():
            patches_dir.unlink()
        else:
            shutil.rmtree(patches_dir)
    patches_dir.mkdir(parents=True, exist_ok=True)
    for rel in [
        "logs",
        "workspaces",
        "successful",
        "unsuccessful",
        "_test_mode",
    ]:
        (patches_dir / rel).mkdir(parents=True, exist_ok=True)

    _run_git(["git", "init"], cwd=live_repo)
    _run_git(["git", "add", "-A"], cwd=live_repo)

    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "BadGuys"
    env["GIT_AUTHOR_EMAIL"] = "badguys@example.invalid"
    env["GIT_COMMITTER_NAME"] = "BadGuys"
    env["GIT_COMMITTER_EMAIL"] = "badguys@example.invalid"
    # Fixed timestamp for deterministic commit SHA across environments.
    env["GIT_AUTHOR_DATE"] = "2000-01-01T00:00:00+00:00"
    env["GIT_COMMITTER_DATE"] = "2000-01-01T00:00:00+00:00"

    cp = subprocess.run(
        [
            "git",
            "commit",
            "--allow-empty",
            "-m",
            "badguys: hermetic live repo bootstrap",
            "--no-gpg-sign",
        ],
        cwd=str(live_repo),
        capture_output=True,
        text=True,
        env=env,
    )
    if cp.returncode != 0:
        msg = (cp.stdout or "").rstrip("\n") + "\n" + (cp.stderr or "").rstrip("\n")
        raise SystemExit(f"FAIL: git commit failed in hermetic live repo\n{msg}")

    # The runner expects to compare main vs origin/main for up-to-date checks.
    # Provide a deterministic local origin/main ref with zero divergence.
    _run_git(["git", "branch", "-M", "main"], cwd=live_repo)
    _run_git(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=live_repo)

    return live_repo



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
        from badguys.ipc_result_reader import read_ipc_result

        socket_path = ctx.cfg.patches_dir / f"am_patch_ipc_{ctx.cfg.issue_id}.sock"

        def _run_reader() -> None:
            ipc_holder["result"] = read_ipc_result(
                socket_path,
                connect_timeout_s=3.0,
                total_timeout_s=0.0,
            )

        ipc_thread = threading.Thread(target=_run_reader, name="badguys_ipc_reader", daemon=True)
        ipc_thread.start()


    # Hermetic git bootstrap: nested am_patch runner invocations require a git working tree.
    if cwd == ctx.repo_root and _is_am_patch_runner_argv(argv):
        cwd = ctx.live_repo_root

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
    repo_root = ctx.live_repo_root
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


def _run_test_plan(test, ctx: Ctx) -> bool:
    from badguys._util import (
        CmdStep,
        ExpectPathExists,
        FuncStep,
        Plan,
    )

    name = getattr(test, "name", "(unknown)")
    try:
        plan_obj = test.run(ctx)
    except SystemExit as e:
        # Treat SystemExit from a test as a deterministic test FAIL, not a suite crash.
        _emit(ctx, level="verbose", test_name=name, text=f"FAIL: {e}\n")
        _emit(ctx, level="verbose", test_name=name, text=f"TEST END {name} FAIL\n")
        return False
    except Exception:
        # Treat unexpected exceptions from a test as FAIL. Only include traceback in debug.
        ok = False
        if _want(ctx.log_verbosity, "debug") or _want(ctx.console_verbosity, "debug"):
            tb = traceback.format_exc()
            _emit(ctx, level="verbose", test_name=name, text="FAIL: test raised\n" + tb + "\n")
        else:
            exc = traceback.format_exc().strip().splitlines()[-1]
            _emit(ctx, level="verbose", test_name=name, text=f"FAIL: {exc}\n")
        _emit(ctx, level="verbose", test_name=name, text=f"TEST END {name} FAIL\n")
        return False

    if not isinstance(plan_obj, Plan):
        raise SystemExit(f"FAIL: test {name} returned invalid plan type: {type(plan_obj).__name__}")

    ok = True

    _emit(ctx, level="verbose", test_name=name, text=f"TEST BEGIN {name}\n")

    for step in plan_obj.steps:
        if isinstance(step, CmdStep):
            argv = step.argv
            cwd = step.cwd if step.cwd is not None else ctx.repo_root
            _log_banner(ctx, name, "cmd")
            out = _run_cmd_with_heartbeat(ctx, test_name=name, argv=list(argv), cwd=cwd)
            cp = out.cp
            ipc_result = out.ipc_result

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

            if ipc_result is not None and "ok" in ipc_result:
                if not bool(ipc_result.get("ok")):
                    ok = False
                    _emit(
                        ctx,
                        level="verbose",
                        test_name=name,
                        text=(
                            "FAIL: runner ipc ok=false "
                            f"returncode={cp.returncode} expected={step.expect_rc}\n"
                        ),
                    )
            else:
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

    live_repo_root: Optional[Path] = None

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

        live_repo_root = _prepare_hermetic_live_repo(repo_root)

        cfg_live = replace(cfg, patches_dir=live_repo_root / "patches")

        # Debug: log resolved config details
        ctx = Ctx(
            repo_root=repo_root,
            live_repo_root=live_repo_root,
            run_id=run_id,
            central_log=central_log,
            cfg=cfg_live,
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
        if live_repo_root is not None:
            shutil.rmtree(live_repo_root, ignore_errors=True)
        release_lock(repo_root)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
