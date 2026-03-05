from __future__ import annotations

from badguys._util import CmdStep, FuncStep, Plan, acquire_lock, release_lock


def run(ctx) -> Plan:
    lock_path = ctx.repo_root / "patches" / "badguys_test_002.lock"

    def _prep() -> None:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass

    def _hold_lock() -> None:
        acquire_lock(ctx.repo_root, path=lock_path, ttl_seconds=3600, on_conflict="fail")

    def _release() -> None:
        release_lock(ctx.repo_root, path=lock_path)

    # Second attempt must fail when on_conflict=fail.
    argv = [
        "python3",
        "-c",
        (
            "from pathlib import Path;"
            "from badguys._util import acquire_lock;"
            "import sys;"
            "acquire_lock(Path('.').resolve(), path=Path('patches/badguys_test_002.lock'), ttl_seconds=3600, on_conflict='fail')"
        ),
    ]

    return Plan(
        steps=[
            FuncStep(name="prep", fn=_prep),
            FuncStep(name="hold_lock", fn=_hold_lock),
            CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=1),
            FuncStep(name="release", fn=_release),
        ],
        cleanup_paths=[lock_path],
    )


TEST = {
    "name": "test_002_lock_conflict_fail",
    "run": run,
}
