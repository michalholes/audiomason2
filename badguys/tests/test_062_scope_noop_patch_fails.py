
from __future__ import annotations

from pathlib import Path

from badguys._util import CmdStep, Plan, write_patch_script


def run(ctx) -> Plan:
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)

    patch_path = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_scope_noop.py"

    body = """
# Intentionally do nothing.
"""
    write_patch_script(
        patch_path,
        files=["docs/badguys_batch1/noop.txt"],
        body=body,
    )

    argv = ctx.cfg.runner_cmd + [
        ctx.cfg.issue_id,
        "badguys: noop patch fails",
        str(patch_path),
    ]

    return Plan(
        steps=[CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=1)],
        cleanup_paths=[patch_path],
    )


TEST = {
    "name": "test_062_scope_noop_patch_fails",
    "makes_commit": False,
    "run": run,
}
