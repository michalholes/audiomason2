#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
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

    def central_log_path(self, run_id: str) -> Path:
        rel = self.central_log_pattern.format(run_id=run_id)
        return self.repo_root / Path(rel)


@dataclass
class Ctx:
    repo_root: Path
    run_id: str
    central_log: Path
    cfg: SuiteCfg

    def step_log_path(self, test_name: str) -> Path:
        return self.cfg.logs_dir / f"{self.run_id}__{test_name}.log"


def _load_config(repo_root: Path, config_path: Path) -> dict:
    p = repo_root / config_path
    if not p.exists():
        return {}
    return tomllib.loads(p.read_text(encoding="utf-8"))


def _make_cfg(repo_root: Path, config_path: Path, cli_runner_verbosity: Optional[str]) -> SuiteCfg:
    raw = _load_config(repo_root, config_path)
    suite = raw.get("suite", {})
    lock = raw.get("lock", {})

    issue_id = str(suite.get("issue_id", "666"))
    runner_cmd = [str(x) for x in suite.get("runner_cmd", ["python3", "scripts/am_patch.py"])]
    runner_verbosity = cli_runner_verbosity if cli_runner_verbosity is not None else str(suite.get("runner_verbosity", "quiet"))
    runner_verbosity = runner_verbosity.strip()
    if runner_verbosity:
        runner_cmd = runner_cmd + [f"--verbosity={runner_verbosity}"]


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
        import shutil

        shutil.rmtree(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    central = cfg.central_log_path(run_id)
    central.parent.mkdir(parents=True, exist_ok=True)
    central.write_text(f"badguys run_id={run_id}\n", encoding="utf-8")
    return central


def run_test_adaptive(test, ctx: Ctx) -> bool:
    try:
        return bool(test.run(ctx))
    except TypeError:
        pass

    try:
        return bool(test.run(ctx.repo_root, ctx.run_id, ctx.central_log))
    except TypeError:
        pass

    return bool(
        test.run(
            repo_root=ctx.repo_root,
            run_id=ctx.run_id,
            central_log=ctx.central_log,
        )
    )


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python3 badguys.py")
    ap.add_argument("--config", default="badguys/config.toml", help="Config path (repo-relative)")
    ap.add_argument("--commit-limit", type=int, default=None, help="Override commit_limit from config")
    ap.add_argument(
        "--runner-verbosity",
        default=None,
        choices=["debug", "verbose", "normal", "quiet"],
        help="Override runner verbosity (passed as --verbosity=<mode>)",
    )
    ap.add_argument("--include", action="append", default=[], help="Run only named tests (repeatable)")
    ap.add_argument("--exclude", action="append", default=[], help="Skip named tests (repeatable)")
    ap.add_argument("--list-tests", action="store_true", help="List discovered tests and exit")
    args = ap.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    _ensure_repo_root_in_syspath(repo_root)

    cfg = _make_cfg(repo_root, Path(args.config), args.runner_verbosity)
    run_id = time.strftime("%Y%m%d_%H%M%S")

    from badguys.tests import discover_tests
    from badguys.tests._util import acquire_lock, fail_commit_limit, print_result, release_lock

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

        commit_limit = int(getattr(tests, "commit_limit", 1))
        commit_tests = [t for t in tests if bool(getattr(t, "makes_commit", False))]
        if len(commit_tests) > commit_limit:
            fail_commit_limit(central_log, commit_limit, commit_tests)

        ctx = Ctx(repo_root=repo_root, run_id=run_id, central_log=central_log, cfg=cfg)

        ok_all = True
        for idx, t in enumerate(tests):
            ok = run_test_adaptive(t, ctx)
            print_result(t.name, ok)
            if not ok:
                ok_all = False
                if idx == 0 and bool(getattr(tests, "abort_on_guard_fail", False)):
                    break

        return 0 if ok_all else 1
    finally:
        release_lock(repo_root)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
