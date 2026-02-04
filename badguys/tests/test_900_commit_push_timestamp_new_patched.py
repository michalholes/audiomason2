from __future__ import annotations

import re
import subprocess
import zipfile
from pathlib import Path

from badguys._util import ExpectPathExists, FuncStep, Plan, now_stamp, write_git_add_file_patch, write_text


def _write_git_replace_second_line_patch(rel_path: str, old_line: str, new_line: str) -> str:
    if not old_line.endswith("\n"):
        old_line += "\n"
    if not new_line.endswith("\n"):
        new_line += "\n"
    context_line = "badguys commit marker\n"
    return (
        f"diff --git a/{rel_path} b/{rel_path}\n"
        f"index 1111111..2222222 100644\n"
        f"--- a/{rel_path}\n"
        f"+++ b/{rel_path}\n"
        f"@@ -1,2 +1,2 @@\n"
        f" {context_line}"
        f"-{old_line}"
        f"+{new_line}"
    )


def run(ctx) -> Plan:
    patches_dir = ctx.cfg.patches_dir
    patches_dir.mkdir(parents=True, exist_ok=True)

    issue_id = ctx.cfg.issue_id
    stamp = now_stamp()

    seed_rel = "src/audiomason/_badguys_seed_fail.py"
    seed_text = "def oops(:\n"
    seed_patch = patches_dir / f"issue_{issue_id}__badguys_seed_fail__{stamp}.patch"

    bundle_name = f"issue_{issue_id}__badguys_latest_bundle__{stamp}.zip"
    unsuccessful_dir = ctx.repo_root / "patches" / "unsuccessful"
    unsuccessful_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = unsuccessful_dir / bundle_name

    marker_rel = "badguys/artifacts/commit_marker.txt"
    ws_repo = ctx.repo_root / "patches" / "workspaces" / f"issue_{issue_id}" / "repo"
    ws_marker = ws_repo / marker_rel

    inner_patch_name = f"issue_{issue_id}__badguys_fix_marker__{stamp}.patch"
    inner_patch_path = patches_dir / inner_patch_name

    # RUN #1: create workspace by applying a patch that will fail gates.
    write_git_add_file_patch(seed_patch, seed_rel, seed_text)

    argv1 = ctx.cfg.runner_cmd + [
        issue_id,
        "badguys: seed run to create workspace",
        str(seed_patch),
    ]

    def _run_cmd_capture(argv: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(argv, cwd=str(ctx.repo_root), capture_output=True, text=True)

    def _assert_run1_fails() -> None:
        cp = _run_cmd_capture(argv1)
        if cp.returncode == 0:
            combined = (cp.stdout or "") + "\n" + (cp.stderr or "")
            raise AssertionError("RUN #1 unexpectedly succeeded (rc=0). Output:\n" + combined)

    def _prepare_between_runs() -> None:
        # Prepare commit marker inside the workspace tree.
        ws_marker.parent.mkdir(parents=True, exist_ok=True)
        write_text(ws_marker, "badguys commit marker\ntest\n")

        # Remove seed file inside workspace before run #2.
        try:
            (ws_repo / seed_rel).unlink()
        except FileNotFoundError:
            pass

        # Create the "latest" bundle: update marker second line from 'test' to a unique timestamp.
        replace_patch_txt = _write_git_replace_second_line_patch(marker_rel, "test", stamp)
        write_text(inner_patch_path, replace_patch_txt)

        with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(inner_patch_path, arcname=inner_patch_name)

    # RUN #2: apply latest bundle using -l.
    argv2 = ctx.cfg.runner_cmd + [
        issue_id,
        "badguys: apply latest bundle",
        str(bundle_path),
        "-l",
    ]

    def _assert_run2_success() -> None:
        cp = _run_cmd_capture(argv2)
        combined = (cp.stdout or "") + "\n" + (cp.stderr or "")
        if cp.returncode != 0:
            raise AssertionError(f"RUN #2 failed: rc={cp.returncode}. Output:\n" + combined)
        if "RESULT: SUCCESS" not in combined:
            raise AssertionError("RUN #2 missing success marker: 'RESULT: SUCCESS'. Output:\n" + combined)
        m = re.search(r"^COMMIT:\s*([0-9a-f]{40})\b", combined, flags=re.MULTILINE)
        if not m:
            raise AssertionError("RUN #2 missing/invalid commit SHA line (expected 'COMMIT: <40-hex>'). Output:\n" + combined)
        if "PUSH: OK" not in combined:
            raise AssertionError("RUN #2 missing push marker: 'PUSH: OK'. Output:\n" + combined)

    return Plan(
        steps=[
            FuncStep(name="run #1 (seed): must fail (rc!=0)", fn=_assert_run1_fails),
            ExpectPathExists(path=ws_repo),
            FuncStep(name="prepare workspace marker + latest bundle", fn=_prepare_between_runs),
            FuncStep(name="run #2 (apply latest): must succeed + emit SUCCESS/COMMIT/PUSH", fn=_assert_run2_success),
        ],
        cleanup_paths=[seed_patch, inner_patch_path, bundle_path],
    )


TEST = {
    "name": "test_900_commit_push_timestamp",
    "makes_commit": True,
    "run": run,
}
