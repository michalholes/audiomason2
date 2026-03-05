
from __future__ import annotations

from pathlib import Path

from badguys._util import CmdStep, Plan, write_patch_script


def run(ctx) -> Plan:
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)

    patch_path = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_scope_a.py"

    body = """
(REPO / 'docs/badguys_batch1/a_declared.txt').parent.mkdir(parents=True, exist_ok=True)
(REPO / 'docs/badguys_batch1/a_declared.txt').write_text('declared\\n', encoding='utf-8')
(REPO / 'docs/badguys_batch1/a_undeclared.txt').write_text('undeclared\\n', encoding='utf-8')
"""
    write_patch_script(
        patch_path,
        files=["docs/badguys_batch1/a_declared.txt"],
        body=body,
    )

    argv = ctx.cfg.runner_cmd + [
        "--test-mode",
        "-a",
        ctx.cfg.issue_id,
        "badguys: -a allows undeclared",
        str(patch_path),
    ]

    return Plan(
        steps=[CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=0)],
        cleanup_paths=[patch_path],
    )


TEST = {
    "name": "test_064_a_allows_undeclared",
    "makes_commit": False,
    "run": run,
}
