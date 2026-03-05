from __future__ import annotations

from pathlib import Path

from badguys._util import CmdStep, FuncStep, Plan, acquire_lock, release_lock


def run(ctx) -> Plan:
    lock_path = ctx.repo_root / "patches" / "badguys_test_001.lock"

    def _prep() -> None:
        # Ensure clean start.
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass

    def _acquire() -> None:
        acquire_lock(ctx.repo_root, path=lock_path, ttl_seconds=3600, on_conflict="fail")

    def _release() -> None:
        release_lock(ctx.repo_root, path=lock_path)

    def _cleanup() -> None:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass

    # We explicitly test create+release via util functions.
    return Plan(
        steps=[
            FuncStep(name="prep", fn=_prep),
            FuncStep(name="acquire", fn=_acquire),
            FuncStep(name="release", fn=_release),
            FuncStep(name="cleanup", fn=_cleanup),
        ],
        cleanup_paths=[lock_path],
    )


TEST = {
    "name": "test_001_lock_create_and_release",
    "run": run,
}
