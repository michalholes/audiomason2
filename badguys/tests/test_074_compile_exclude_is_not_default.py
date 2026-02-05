from __future__ import annotations

from pathlib import Path

from badguys._util import CmdStep, FuncStep, Plan, assert_file_contains, assert_file_not_contains, write_git_add_file_patch


def _make_patch(path: Path) -> None:
    # Invalid .py under a directory that is used by other tests only when compile_exclude is explicitly set.
    rel = "scripts/badguys_batch1_excluded/syntax_error_not_default.py"
    write_git_add_file_patch(path, rel, "def oops(:\n    pass\n")


def run(ctx) -> Plan:
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)

    patch_path = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_compile_exclude_not_default.patch"
    _make_patch(patch_path)

    argv = ctx.cfg.runner_cmd + [
        "--test-mode",
        ctx.cfg.issue_id,
        "badguys: compile_exclude is not default",
        str(patch_path),
    ]

    def _assert() -> None:
        log_path = ctx.step_log_path("test_074_compile_exclude_is_not_default")
        assert_file_contains(log_path, "GATE: compile")
        assert_file_not_contains(log_path, "GATE: RUFF")
        assert_file_not_contains(log_path, "GATE: PYTEST")
        assert_file_not_contains(log_path, "GATE: MYPY")

    return Plan(
        steps=[
            CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=1),
            FuncStep(name="assert_compile_stops_without_exclude", fn=_assert),
        ],
        cleanup_paths=[patch_path],
    )


TEST = {
    "name": "test_074_compile_exclude_is_not_default",
    "makes_commit": False,
    "run": run,
}
