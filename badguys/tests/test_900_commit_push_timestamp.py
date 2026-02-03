from __future__ import annotations

from pathlib import Path

from badguys.tests._util import append_log, now_stamp, run_cmd, write_text


def _make_patch_script(path: Path, marker_rel: str, stamp: str) -> None:
    # Minimal patch script for am_patch: declares exactly one file.
    code = f"""from __future__ import annotations

from datetime import datetime
from pathlib import Path


FILES = ["{marker_rel}"]


def apply(repo_root: Path) -> None:
    p = repo_root / "{marker_rel}"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "badguys commit marker\\n" + f"timestamp: {stamp}\\n",
        encoding="utf-8",
    )
"""
    write_text(path, code)


def run(ctx) -> bool:
    step_log = ctx.step_log_path("test_900_commit_push_timestamp")
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)
    stamp = now_stamp()
    marker_rel = "badguys/artifacts/commit_marker.txt"
    patch_script = patch_dir / f"issue_{ctx.cfg.issue_id}__badguys_commit_timestamp__{stamp}.py"
    try:
        _make_patch_script(patch_script, marker_rel, stamp)
        argv = ctx.cfg.runner_cmd + [
            ctx.cfg.issue_id,
            "badguys: commit+push timestamp",
            str(patch_script),
        ]
        cp = run_cmd(argv, cwd=ctx.repo_root)
        append_log(step_log, cp)
        return cp.returncode == 0
    finally:
        try:
            patch_script.unlink()
        except FileNotFoundError:
            pass


TEST = {
    "name": "test_900_commit_push_timestamp",
    "makes_commit": True,
    "run": run,
}
