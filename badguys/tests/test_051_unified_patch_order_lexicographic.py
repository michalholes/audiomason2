
from __future__ import annotations

from pathlib import Path

from badguys._util import CmdStep, Plan, write_git_add_file_patch, write_zip


def run(ctx) -> Plan:
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)

    # Two patches adding the same file with different content; lexicographic order decides final content.
    p1 = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_order_a.patch"
    p2 = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_order_b.patch"
    rel = "docs/badguys_batch1/order.txt"
    write_git_add_file_patch(p1, rel, "first")
    write_git_add_file_patch(p2, rel, "second")

    zip_path = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_order.zip"
    # Ensure internal names sort so that a/1.patch is first, b/2.patch second.
    write_zip(
        zip_path,
        [
            ("a/1.patch", p1.read_bytes()),
            ("b/2.patch", p2.read_bytes()),
        ],
    )

    argv = ctx.cfg.runner_cmd + [
        "--test-mode",
        ctx.cfg.issue_id,
        "badguys: unified zip order",
        str(zip_path),
    ]

    return Plan(
        steps=[CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=0)],
        cleanup_paths=[p1, p2, zip_path],
    )


TEST = {
    "name": "test_051_unified_patch_order_lexicographic",
    "makes_commit": False,
    "run": run,
}
