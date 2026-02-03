from __future__ import annotations

import difflib
from pathlib import Path

from badguys.tests._util import append_log, now_stamp, run_cmd, write_text


def _make_patch(repo_root: Path, path: Path, marker_rel: str, stamp: str) -> None:
    marker_path = repo_root / marker_rel
    if marker_path.exists():
        old_text = marker_path.read_text(encoding="utf-8")
        if old_text and not old_text.endswith("\n"):
            old_text = old_text + "\n"
        old_lines = old_text.splitlines(keepends=True)

        new_lines = list(old_lines)
        new_lines.append(f"timestamp: {stamp}\n")

        diff_lines = list(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{marker_rel}",
                tofile=f"b/{marker_rel}",
                lineterm="",
            )
        )

        content = "diff --git a/{0} b/{0}\n".format(marker_rel) + "\n".join(diff_lines) + "\n"
    else:
        new_lines = ["badguys commit marker\n", f"timestamp: {stamp}\n"]
        diff_lines = list(
            difflib.unified_diff(
                [],
                new_lines,
                fromfile="/dev/null",
                tofile=f"b/{marker_rel}",
                lineterm="",
            )
        )
        content = (
            "diff --git a/{0} b/{0}\n".format(marker_rel)
            + "new file mode 100644\n"
            + "\n".join(diff_lines)
            + "\n"
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
        _make_patch(ctx.repo_root, patch_path, marker_rel, stamp)
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
