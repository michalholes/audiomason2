
from __future__ import annotations

from pathlib import Path

from badguys._util import CmdStep, FuncStep, Plan, assert_path_missing, write_git_add_file_patch


def _make_patch(path: Path) -> None:
    rel = "docs/badguys_batch1/test_mode_hard_stop_marker.txt"
    write_git_add_file_patch(path, rel, "marker")


def run(ctx) -> Plan:
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)
    patch_path = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_test_mode_hard_stop.patch"
    _make_patch(patch_path)

    argv = ctx.cfg.runner_cmd + [
        "--test-mode",
        ctx.cfg.issue_id,
        "badguys: test-mode hard stop",
        str(patch_path),
    ]

    ws_dir = ctx.cfg.patches_dir / "workspaces" / f"issue_{ctx.cfg.issue_id}"
    fail_zip = ctx.cfg.patches_dir / "patched.zip"

    def _assert() -> None:
        assert_path_missing(ws_dir)
        assert_path_missing(fail_zip)

    return Plan(
        steps=[
            CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=0),
            FuncStep(name="assert_no_workspace_no_archives", fn=_assert),
        ],
        cleanup_paths=[patch_path],
    )


TEST = {
    "name": "test_040_test_mode_hard_stop_no_archives",
    "makes_commit": False,
    "run": run,
}
