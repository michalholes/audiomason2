from __future__ import annotations

from badguys._util import CmdStep, Plan


def run(ctx) -> Plan:
    # Exclude one test; suite should run all remaining, including guard.
    argv = [
        "python3",
        "badguys/badguys.py",
        "--exclude",
        "test_030_show_config",
        "--commit-limit",
        "0",
        "-q",
    ]
    return Plan(steps=[CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=0)])


TEST = {
    "name": "test_012_exclude_single",
    "run": run,
}
