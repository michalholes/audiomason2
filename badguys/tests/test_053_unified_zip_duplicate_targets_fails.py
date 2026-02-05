from __future__ import annotations

from pathlib import Path

from badguys._util import CmdStep, FuncStep, Plan, assert_file_contains, write_git_add_file_patch, write_zip


def run(ctx) -> Plan:
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)

    rel = "docs/badguys_batch1/unified_duplicate_target.txt"

    patch_a = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_dup_a.patch"
    patch_b = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_dup_b.patch"

    write_git_add_file_patch(patch_a, rel, "A")
    write_git_add_file_patch(patch_b, rel, "B")

    zip_path = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_unified_duplicate_targets.zip"
    write_zip(
        zip_path,
        [
            ("a.patch", patch_a.read_bytes()),
            ("b.patch", patch_b.read_bytes()),
        ],
    )

    argv = ctx.cfg.runner_cmd + [
        "--test-mode",
        ctx.cfg.issue_id,
        "badguys: unified zip duplicate targets must fail",
        str(zip_path),
    ]

    def _assert() -> None:
        log_path = ctx.step_log_path("test_053_unified_zip_duplicate_targets_fails")
        assert_file_contains(log_path, rel)

    return Plan(
        steps=[
            CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=1),
            FuncStep(name="assert_rel_path_in_log", fn=_assert),
        ],
        cleanup_paths=[patch_a, patch_b, zip_path],
    )


TEST = {
    "name": "test_053_unified_zip_duplicate_targets_fails",
    "makes_commit": False,
    "run": run,
}
