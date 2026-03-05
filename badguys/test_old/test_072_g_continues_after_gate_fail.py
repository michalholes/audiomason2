from __future__ import annotations

from pathlib import Path

from badguys._util import (
    CmdStep,
    FuncStep,
    Plan,
    assert_file_contains,
    write_git_add_file_patch,
    write_zip,
)


def run(ctx) -> Plan:
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)

    inner_patch_path = patch_dir / "bg_072_src_test_py.patch"
    zip_path = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_gates_continue.zip"

    # Add a file under src/ so that compile/ruff/mypy gates see it.
    # Intentionally invalid syntax so the compile gate fails.
    write_git_add_file_patch(inner_patch_path, "src/test.py", "oops = )\n")

    patch_bytes = inner_patch_path.read_bytes()
    write_zip(zip_path, entries=[("inner.patch", patch_bytes)])

    argv = ctx.cfg.runner_cmd + [
        "-g",
        "--test-mode",
        ctx.cfg.issue_id,
        "badguys: -g continues after gate fail (compile)",
        str(zip_path),
    ]

    def _assert() -> None:
        per_run_log = ctx.step_log_path("test_072_g_continues_after_gate_fail")
        text = per_run_log.read_text(encoding="utf-8", errors="replace")
        runner_log: Path | None = None
        for line in text.splitlines():
            if line.startswith("LOG: "):
                runner_log = Path(line[len("LOG: ") :].strip())
                break
        if runner_log is None:
            raise AssertionError("missing LOG: <runner_log_path> line in per-run log")

        # Gate fail must be *allowed* under -g, and the runner must still succeed overall.
    return Plan(
        steps=[
            CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=0),
            FuncStep(name="assert_gates_continued", fn=_assert),
        ],
        cleanup_paths=[inner_patch_path, zip_path],
    )


TEST = {
    "name": "test_072_g_continues_after_gate_fail",
    "makes_commit": False,
    "run": run,
}
