
from __future__ import annotations

from pathlib import Path

from badguys._util import CmdStep, FuncStep, Plan, assert_path_missing, write_git_add_file_patch


def _make_patch(path: Path) -> None:
    # Add a syntactically-invalid .py under scripts/ so COMPILE gate fails.
    rel = "scripts/badguys_batch1_compile_fail.py"
    write_git_add_file_patch(path, rel, "def oops(:\n    pass\n")


def run(ctx) -> Plan:
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)
    patch_path = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_test_mode_compile_fail.patch"
    _make_patch(patch_path)

    argv = ctx.cfg.runner_cmd + [
        "--test-mode",
        ctx.cfg.issue_id,
        "badguys: test-mode cleanup on fail",
        str(patch_path),
    ]

    ws_dir = ctx.cfg.patches_dir / "workspaces" / f"issue_{ctx.cfg.issue_id}"
    fail_zip = ctx.cfg.patches_dir / "patched.zip"

    def _assert() -> None:
        assert_path_missing(ws_dir)
        assert_path_missing(fail_zip)

    return Plan(
        steps=[
            CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=1),
            FuncStep(name="assert_cleanup", fn=_assert),
        ],
        cleanup_paths=[patch_path],
    )


TEST = {
    "name": "test_041_test_mode_cleanup_on_fail",
    "makes_commit": False,
    "run": run,
}
