from __future__ import annotations

from pathlib import Path

from badguys.tests._util import append_log, run_cmd, write_git_add_file_patch


def _make_patch(path: Path) -> None:
    # Add a new file in the workspace only. In --test-mode this must not affect live repo.
    rel = "badguys/tmp/test_mode_smoke_marker.txt"
    write_git_add_file_patch(path, rel, "badguys test-mode smoke")


def run(ctx) -> bool:
    step_log = ctx.step_log_path("test_000_test_mode_smoke")
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)
    patch_path = patch_dir / f"issue_{ctx.cfg.issue_id}__badguys_test_mode_smoke.patch"
    try:
        _make_patch(patch_path)
        argv = ctx.cfg.runner_cmd + [
            "--test-mode",
            ctx.cfg.issue_id,
            "badguys: test-mode smoke",
            str(patch_path),
        ]
        cp = run_cmd(argv, cwd=ctx.repo_root)
        append_log(step_log, cp)
        return cp.returncode == 0
    finally:
        try:
            patch_path.unlink()
        except FileNotFoundError:
            pass


TEST = {
    "name": "test_000_test_mode_smoke",
    "makes_commit": False,
    "run": run,
}
