from __future__ import annotations

from badguys._util import CmdStep, Plan


def run(ctx) -> Plan:
    # Include and exclude the same test. Under current suite policy, this leads to
    # missing guard (since include filter removes guard too) and must fail deterministically.
    argv = [
        "python3",
        "badguys/badguys.py",
        "--include",
        "test_030_show_config",
        "--exclude",
        "test_030_show_config",
        "--commit-limit",
        "0",
        "-q",
    ]
    return Plan(steps=[CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=1)])


TEST = {
    "name": "test_013_include_exclude_conflict",
    "run": run,
}
