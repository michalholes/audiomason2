from __future__ import annotations

from badguys._util import CmdStep, Plan


def run(ctx) -> Plan:
    argv = ctx.cfg.runner_cmd + ["-h"]
    return Plan(steps=[CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=0)])


TEST = {
    "name": "test_010_help_short",
    "makes_commit": False,
    "run": run,
}
