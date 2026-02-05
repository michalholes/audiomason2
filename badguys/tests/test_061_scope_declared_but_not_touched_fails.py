
from __future__ import annotations

from pathlib import Path

from badguys._util import CmdStep, Plan, write_patch_script


def run(ctx) -> Plan:
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)

    patch_path = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_scope_declared_not_touched.py"

    body = """
(REPO / 'docs/badguys_batch1/scope_touched.txt').parent.mkdir(parents=True, exist_ok=True)
(REPO / 'docs/badguys_batch1/scope_touched.txt').write_text('touched\n', encoding='utf-8')
# declared_untouched.txt is declared but intentionally not touched
"""
    write_patch_script(
        patch_path,
        files=[
            "docs/badguys_batch1/declared_untouched.txt",
            "docs/badguys_batch1/scope_touched.txt",
        ],
        body=body,
    )

    argv = ctx.cfg.runner_cmd + [
        ctx.cfg.issue_id,
        "badguys: scope declared but not touched fails",
        str(patch_path),
    ]

    return Plan(
        steps=[CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=1)],
        cleanup_paths=[patch_path],
    )


TEST = {
    "name": "test_061_scope_declared_but_not_touched_fails",
    "makes_commit": False,
    "run": run,
}
