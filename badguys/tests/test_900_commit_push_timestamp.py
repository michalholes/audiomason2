from __future__ import annotations

from pathlib import Path

from badguys.tests._util import append_log, now_stamp, run_cmd, write_text


def _make_patch(path: Path, marker_rel: str, stamp: str) -> None:
    # Unified diff patch that appends a new timestamp line.
    # It relies on the first two lines being stable.
    content = (
        f"diff --git a/{marker_rel} b/{marker_rel}\n"
        f"index 1111111..2222222 100644\n"
        f"--- a/{marker_rel}\n"
        f"+++ b/{marker_rel}\n"
        f"@@ -1,2 +1,3 @@\n"
        f" badguys commit marker\n"
        f" timestamp: INITIAL\n"
        f"+timestamp: {stamp}\n"
    )
    write_text(path, content)


def run(ctx) -> bool:
    step_log = ctx.step_log_path("test_900_commit_push_timestamp")
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)
    stamp = now_stamp()
    marker_rel = "badguys/artifacts/commit_marker.txt"
    patch_path = patch_dir / f"issue_{ctx.cfg.issue_id}__badguys_commit_timestamp__{stamp}.patch"
    try:
        _make_patch(patch_path, marker_rel, stamp)
        argv = ctx.cfg.runner_cmd + [
            ctx.cfg.issue_id,
            "badguys: commit+push timestamp",
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
    "name": "test_900_commit_push_timestamp",
    "makes_commit": True,
    "run": run,
}
