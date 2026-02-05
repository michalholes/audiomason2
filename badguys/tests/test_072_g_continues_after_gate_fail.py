
from __future__ import annotations

from pathlib import Path

from badguys._util import CmdStep, FuncStep, Plan, assert_file_contains, write_patch_script


def run(ctx) -> Plan:
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)

    patch_path = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_gates_continue.py"

    body = """
# Produce a ruff violation in scripts/ (line too long), but keep valid syntax for compile.
p = REPO / 'scripts' / 'badguys_batch1_ruff_fail.py'
p.write_text("x = '%s'" % ("a"*200) + "\n", encoding="utf-8")
"""
    write_patch_script(patch_path, files=["scripts/badguys_batch1_ruff_fail.py"], body=body)

    argv = ctx.cfg.runner_cmd + [
        "-g",
        "--test-mode",
        ctx.cfg.issue_id,
        "badguys: -g continues after ruff fail",
        str(patch_path),
    ]

    def _assert() -> None:
        per_run_log = ctx.step_log_path("test_072_g_continues_after_gate_fail")
        text = per_run_log.read_text(encoding="utf-8", errors="replace")
        runner_log: Path | None = None
        for line in text.splitlines():
            if line.startswith("LOG: "):
                runner_log = Path(line[len("LOG: "):].strip())
                break
        if runner_log is None:
            raise AssertionError("missing LOG: <runner_log_path> line in per-run log")
        assert_file_contains(runner_log, "GATE: RUFF")
        assert_file_contains(runner_log, "GATE: PYTEST")
        assert_file_contains(runner_log, "GATE: MYPY")

    return Plan(
        steps=[
            CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=1),
            FuncStep(name="assert_gates_continued", fn=_assert),
        ],
        cleanup_paths=[patch_path],
    )


TEST = {
    "name": "test_072_g_continues_after_gate_fail",
    "makes_commit": False,
    "run": run,
}
