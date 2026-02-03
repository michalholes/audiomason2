#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from dataclasses import dataclass

# --- Context object -------------------------------------------------

@dataclass
class Ctx:
    repo_root: Path
    run_id: str
    central_log: Path
    logs_dir: Path

    def step_log_path(self, test_name: str) -> Path:
        return self.logs_dir / f"{self.run_id}__{test_name}.log"


# --- Adaptive test runner ------------------------------------------

def run_test_adaptive(test, ctx: Ctx) -> bool:
    # preferred: run(ctx)
    try:
        return bool(test.run(ctx))
    except TypeError:
        pass

    # legacy: run(repo_root, run_id, central_log)
    try:
        return bool(test.run(ctx.repo_root, ctx.run_id, ctx.central_log))
    except TypeError:
        pass

    # legacy keyword
    return bool(
        test.run(
            repo_root=ctx.repo_root,
            run_id=ctx.run_id,
            central_log=ctx.central_log,
        )
    )


# --- Main -----------------------------------------------------------

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit-limit", type=int, default=1)
    ap.add_argument("--include", action="append", default=[])
    ap.add_argument("--exclude", action="append", default=[])
    ap.add_argument("--list-tests", action="store_true")
    args = ap.parse_args(argv)

    repo_root = Path(".").resolve()
    run_id = time.strftime("%Y%m%d_%H%M%S")

    from badguys.tests import discover_tests
    from badguys.tests._util import acquire_lock, release_lock

    acquire_lock()
    try:
        logs_dir = repo_root / "patches/badguys_logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        central_log = repo_root / f"patches/badguys_{run_id}.log"
        central_log.write_text(f"badguys run {run_id}\n")

        tests = discover_tests(
            repo_root=repo_root,
            include=args.include,
            exclude=args.exclude,
        )

        if args.list_tests:
            for t in tests:
                print(t["name"])
            return 0

        commit_tests = [t for t in tests if t.get("makes_commit")]
        if len(commit_tests) > args.commit_limit:
            print(
                f"FAIL: commit_limit exceeded "
                f"(selected={len(commit_tests)} limit={args.commit_limit})",
                file=sys.stderr,
            )
            for t in commit_tests:
                print(f" - {t['name']}", file=sys.stderr)
            return 1

        ctx = Ctx(
            repo_root=repo_root,
            run_id=run_id,
            central_log=central_log,
            logs_dir=logs_dir,
        )

        ok_all = True
        for t in tests:
            name = t["name"]
            ok = run_test_adaptive(t, ctx)
            status = "OK" if ok else "FAIL"
            print(f"badguys::{name} ... {status}")
            if not ok:
                ok_all = False

        return 0 if ok_all else 1

    finally:
        release_lock()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
