from __future__ import annotations

from badguys._util import CmdStep, FuncStep, Plan, assert_file_not_contains


def run(ctx) -> Plan:
    argv = ctx.cfg.runner_cmd + [
        "--test-mode",
        "--verbosity=loud",
        ctx.cfg.issue_id,
        "badguys: invalid runner verbosity must fail cleanly",
        "DOES_NOT_MATTER",
    ]

    def _assert() -> None:
        log_path = ctx.step_log_path("test_031_invalid_runner_verbosity_fails_cleanly")
        assert_file_not_contains(log_path, "Traceback")

    return Plan(
        steps=[
            CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=2),
            FuncStep(name="assert_no_traceback", fn=_assert),
        ],
    )


TEST = {
    "name": "test_031_invalid_runner_verbosity_fails_cleanly",
    "makes_commit": False,
    "run": run,
}
