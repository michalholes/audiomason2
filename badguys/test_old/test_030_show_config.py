from __future__ import annotations

from badguys._util import CmdStep, Plan


def run(ctx) -> Plan:
    argv = ctx.cfg.runner_cmd + ["-c"]
    return Plan(steps=[CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=0)])


TEST = {
    "name": "test_030_show_config",
    "makes_commit": False,
    "run": run,
}
