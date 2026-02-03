from __future__ import annotations

from pathlib import Path

from badguys.tests._util import append_log, now_stamp, run_cmd, write_git_add_file_patch


def run(ctx) -> bool:
    step_log = ctx.step_log_path("test_100_rerun_latest_l")

    unsucc_dir = ctx.cfg.patches_dir / "unsuccessful"
    unsucc_dir.mkdir(parents=True, exist_ok=True)

    # Create a fresh archived patch inside patches/unsuccessful so -l can pick it...
    stamp = now_stamp()
    archived_patch = unsucc_dir / f"issue_{ctx.cfg.issue_id}__badguys_rerun_latest__{stamp}.patch"
    marker_rel = "badguys/tmp/rerun_latest_marker.txt"

    try:
        write_git_add_file_patch(archived_patch, marker_rel, f"badguys rerun-latest {stamp}")
        argv = ctx.cfg.runner_cmd + [
            "--test-mode",
            "-l",
            ctx.cfg.issue_id,
            "badguys: rerun-latest (-l) smoke",
        ]
        cp = run_cmd(argv, cwd=ctx.repo_root)
        append_log(step_log, cp)
        return cp.returncode == 0
    finally:
        try:
            archived_patch.unlink()
        except FileNotFoundError:
            pass


TEST = {
    "name": "test_100_rerun_latest_l",
    "makes_commit": False,
    "run": run,
}
