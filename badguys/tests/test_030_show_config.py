from __future__ import annotations

from badguys.tests._util import append_log, run_cmd


def run(ctx) -> bool:
    step_log = ctx.step_log_path("test_030_show_config")
    argv = ctx.cfg.runner_cmd + ["-c"]
    cp = run_cmd(argv, cwd=ctx.repo_root)
    append_log(step_log, cp)
    return cp.returncode == 0


TEST = {
    "name": "test_030_show_config",
    "makes_commit": False,
    "run": run,
}
