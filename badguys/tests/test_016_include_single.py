from __future__ import annotations

from badguys._util import CmdStep, Plan


def run(ctx) -> Plan:
    # Suite requires guard test to be present after filtering.
    # Therefore include must include both guard and the target.
    argv = [
        "python3",
        "badguys/badguys.py",
        "--include",
        ctx.cfg.guard_test_name,
        "--include",
        "test_030_show_config",
        "--commit-limit",
        "0",
        "-q",
    ]
    return Plan(steps=[CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=0)])


TEST = {
    "name": "test_011_include_single",
    "run": run,
}
