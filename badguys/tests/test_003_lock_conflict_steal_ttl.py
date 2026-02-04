from __future__ import annotations

import time

from badguys._util import FuncStep, Plan, acquire_lock, release_lock


def run(ctx) -> Plan:
    lock_path = ctx.repo_root / "patches" / "badguys_test_003.lock"

    def _prep_stale_lock() -> None:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        # Write a stale lock content (started far in the past).
        started = int(time.time()) - 10_000
        lock_path.write_text(f"pid=0\nstarted={started}\n", encoding="utf-8")

    def _acquire_steal() -> None:
        acquire_lock(ctx.repo_root, path=lock_path, ttl_seconds=1, on_conflict="steal")

    def _release() -> None:
        release_lock(ctx.repo_root, path=lock_path)

    return Plan(
        steps=[
            FuncStep(name="prep_stale_lock", fn=_prep_stale_lock),
            FuncStep(name="acquire_steal", fn=_acquire_steal),
            FuncStep(name="release", fn=_release),
        ],
        cleanup_paths=[lock_path],
    )


TEST = {
    "name": "test_003_lock_conflict_steal_ttl",
    "run": run,
}
