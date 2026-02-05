
from __future__ import annotations

from pathlib import Path

from badguys._util import CmdStep, FuncStep, Plan, assert_file_contains, write_git_add_file_patch


def _make_patch(path: Path) -> None:
    rel = "scripts/badguys_batch1_excluded/syntax_error.py"
    write_git_add_file_patch(path, rel, "def oops(:\n    pass\n")


def run(ctx) -> Plan:
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)

    patch_path = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_compile_exclude.patch"
    _make_patch(patch_path)

    argv = ctx.cfg.runner_cmd + [
        "--test-mode",
        "--override",
        "compile_exclude=['scripts/badguys_batch1_excluded']",
        ctx.cfg.issue_id,
        "badguys: compile exclude respected",
        str(patch_path),
    ]

    def _assert() -> None:
        log_path = ctx.step_log_path("test_071_compile_exclude_respected")
        assert_file_contains(log_path, "GATE: compile")
        assert_file_contains(log_path, "compile_exclude=['scripts/badguys_batch1_excluded']")

    return Plan(
        steps=[
            CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=0),
            FuncStep(name="assert_compile_exclude_logged", fn=_assert),
        ],
        cleanup_paths=[patch_path],
    )


TEST = {
    "name": "test_071_compile_exclude_respected",
    "makes_commit": False,
    "run": run,
}
