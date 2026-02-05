
from __future__ import annotations

from pathlib import Path

from badguys._util import CmdStep, Plan, write_git_add_file_patch, write_zip


def run(ctx) -> Plan:
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)

    inner_patch_name = "subdir/inner.patch"
    inner_patch_path = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_inner.patch"
    write_git_add_file_patch(inner_patch_path, "docs/badguys_batch1/unified_recursive.txt", "ok")

    zip_path = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_unified_recursive.zip"
    write_zip(zip_path, [(inner_patch_name, inner_patch_path.read_bytes())])

    argv = ctx.cfg.runner_cmd + [
        "--test-mode",
        ctx.cfg.issue_id,
        "badguys: unified zip recursive",
        str(zip_path),
    ]

    return Plan(
        steps=[CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=0)],
        cleanup_paths=[inner_patch_path, zip_path],
    )


TEST = {
    "name": "test_050_unified_patch_zip_recursive_detection",
    "makes_commit": False,
    "run": run,
}
