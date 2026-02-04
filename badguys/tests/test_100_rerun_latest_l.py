from __future__ import annotations

from badguys._util import CmdStep, Plan, now_stamp, write_git_add_file_patch


def run(ctx) -> Plan:
    unsucc_dir = ctx.cfg.patches_dir / "unsuccessful"
    unsucc_dir.mkdir(parents=True, exist_ok=True)

    # Create a fresh archived patch inside patches/unsuccessful so -l can pick it...
    stamp = now_stamp()
    archived_patch = unsucc_dir / f"issue_{ctx.cfg.issue_id}__badguys_rerun_latest__{stamp}.patch"
    marker_rel = "badguys/tmp/rerun_latest_marker.txt"

    write_git_add_file_patch(archived_patch, marker_rel, f"badguys rerun-latest {stamp}")

    argv = ctx.cfg.runner_cmd + [
        "--test-mode",
        "-l",
        ctx.cfg.issue_id,
        "badguys: rerun-latest (-l) smoke",
    ]

    return Plan(
        steps=[CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=0)],
        cleanup_paths=[archived_patch],
    )


TEST = {
    "name": "test_100_rerun_latest_l",
    "makes_commit": False,
    "run": run,
}
