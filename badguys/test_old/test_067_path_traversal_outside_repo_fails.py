from __future__ import annotations

from pathlib import Path

from badguys._util import CmdStep, FuncStep, Plan, write_patch_script


def run(ctx) -> Plan:
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)

    # Sentinel intentionally outside repo_root.
    sentinel = ctx.repo_root.parent / f"badguys_sentinel_issue_{ctx.cfg.issue_id}.txt"
    try:
        sentinel.unlink()
    except FileNotFoundError:
        pass

    patch_path = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_path_traversal_outside_repo.py"

    body = f"""
# Attempt to write outside repo root. This must be rejected by the runner sandbox/scope rules.
outside = (REPO / '..' / {sentinel.name!r}).resolve()
outside.write_text('pwned\n', encoding='utf-8')
"""

    write_patch_script(
        patch_path,
        files=["docs/badguys_batch1/path_traversal_declared_dummy.txt"],
        body=body,
    )

    argv = ctx.cfg.runner_cmd + [
        "--test-mode",
        ctx.cfg.issue_id,
        "badguys: path traversal outside repo must fail",
        str(patch_path),
    ]

    def _assert_sentinel_not_written() -> None:
        if sentinel.exists():
            raise AssertionError(f"runner wrote outside repo: {sentinel}")

    return Plan(
        steps=[
            CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=1),
            FuncStep(name="assert_no_outside_write", fn=_assert_sentinel_not_written),
        ],
        cleanup_paths=[patch_path, sentinel],
    )


TEST = {
    "name": "test_067_path_traversal_outside_repo_fails",
    "makes_commit": False,
    "run": run,
}
