
from __future__ import annotations

from pathlib import Path

from badguys._util import CmdStep, FuncStep, Plan, assert_file_contains, assert_file_not_contains, write_git_add_file_patch


def _make_patch(path: Path) -> None:
    # Add invalid .py under scripts/ so compile gate fails first.
    rel = "scripts/badguys_batch1_gate_order.py"
    write_git_add_file_patch(path, rel, "def oops(:\n    pass\n")


def run(ctx) -> Plan:
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)

    patch_path = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_gate_order.patch"
    _make_patch(patch_path)

    argv = ctx.cfg.runner_cmd + [
        "--test-mode",
        ctx.cfg.issue_id,
        "badguys: gate order compile first",
        str(patch_path),
    ]

    def _assert() -> None:
        log_path = ctx.step_log_path("test_070_gate_order_is_compile_ruff_pytest_mypy")
        assert_file_contains(log_path, "GATE: compile")
        assert_file_not_contains(log_path, "GATE: RUFF")
        assert_file_not_contains(log_path, "GATE: PYTEST")
        assert_file_not_contains(log_path, "GATE: MYPY")

    return Plan(
        steps=[
            CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=1),
            FuncStep(name="assert_compile_first", fn=_assert),
        ],
        cleanup_paths=[patch_path],
    )


TEST = {
    "name": "test_070_gate_order_is_compile_ruff_pytest_mypy",
    "makes_commit": False,
    "run": run,
}
