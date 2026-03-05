from __future__ import annotations

from pathlib import Path

from badguys._util import CmdStep, Plan, write_git_add_file_patch


def _make_patch(path: Path) -> None:
    # Add a new file in the workspace only. In --test-mode this must not affect live repo.
    rel = "badguys/tmp/test_mode_smoke_marker.txt"
    write_git_add_file_patch(path, rel, "badguys test-mode smoke")


def run(ctx) -> Plan:
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)
    patch_path = patch_dir / f"issue_{ctx.cfg.issue_id}__badguys_test_mode_smoke.patch"

    _make_patch(patch_path)
    argv = ctx.cfg.runner_cmd + [
        "--test-mode",
        ctx.cfg.issue_id,
        "badguys: test-mode smoke",
        str(patch_path),
    ]

    return Plan(
        steps=[CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=0)],
        cleanup_paths=[patch_path],
    )


TEST = {
    "name": "test_000_test_mode_smoke",
    "makes_commit": False,
    "run": run,
}
