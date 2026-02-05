
from __future__ import annotations

from pathlib import Path

from badguys._util import CmdStep, Plan, write_patch_script


def run(ctx) -> Plan:
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)

    patch_path = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_blessed_no_a.py"

    body = """
(REPO / 'docs/badguys_batch1/blessed_driver.txt').parent.mkdir(parents=True, exist_ok=True)
(REPO / 'docs/badguys_batch1/blessed_driver.txt').write_text('ok\\n', encoding='utf-8')

j = REPO / 'audit' / 'results' / 'pytest_junit.xml'
j.parent.mkdir(parents=True, exist_ok=True)
j.write_text('<testsuite/>\\n', encoding='utf-8')
"""
    write_patch_script(
        patch_path,
        files=["docs/badguys_batch1/blessed_driver.txt"],
        body=body,
    )

    argv = ctx.cfg.runner_cmd + [
        ctx.cfg.issue_id,
        "badguys: blessed output without -a",
        str(patch_path),
    ]

    return Plan(
        steps=[CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=0)],
        cleanup_paths=[patch_path],
    )


TEST = {
    "name": "test_063_blessed_gate_output_allowed_without_a",
    "makes_commit": False,
    "run": run,
}
