from __future__ import annotations

from pathlib import Path

from badguys._util import CmdStep, FuncStep, Plan, assert_file_contains, assert_file_not_contains, write_git_add_file_patch


def _make_patch(path: Path) -> None:
    # Add a valid .py that should fail ruff (unused import / unused variable),
    # while still passing compile.
    rel = "scripts/badguys_batch1_gate_ruff_fail.py"
    write_git_add_file_patch(
        path,
        rel,
        "import os\n\n"
        "def ok() -> None:\n"
        "    x = 1\n"
        "    return None\n",
    )


def run(ctx) -> Plan:
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)

    patch_path = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_gate_ruff_fail.patch"
    _make_patch(patch_path)

    argv = ctx.cfg.runner_cmd + [
        "--test-mode",
        ctx.cfg.issue_id,
        "badguys: fail-fast after ruff",
        str(patch_path),
    ]

    def _assert() -> None:
        log_path = ctx.step_log_path("test_073_gate_fail_fast_stops_after_ruff")
        assert_file_contains(log_path, "GATE: compile")
        assert_file_contains(log_path, "GATE: RUFF")
        assert_file_not_contains(log_path, "GATE: PYTEST")
        assert_file_not_contains(log_path, "GATE: MYPY")

    return Plan(
        steps=[
            CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=1),
            FuncStep(name="assert_ruff_fail_fast", fn=_assert),
        ],
        cleanup_paths=[patch_path],
    )


TEST = {
    "name": "test_073_gate_fail_fast_stops_after_ruff",
    "makes_commit": False,
    "run": run,
}
