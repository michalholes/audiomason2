from __future__ import annotations

import subprocess
from pathlib import Path

from badguys._util import CmdStep, FuncStep, Plan, write_patch_script


def _git_status_porcelain(repo_root: Path) -> list[str]:
    cp = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    out = (cp.stdout or "").splitlines()
    return [ln.rstrip("\n") for ln in out if ln.strip()]


def run(ctx) -> Plan:
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)

    patch_path = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_scope_undeclared_index_clean.py"

    body = r"""
(REPO / 'docs/badguys_batch1/scope_declared_index_clean.txt').parent.mkdir(parents=True, exist_ok=True)
(REPO / 'docs/badguys_batch1/scope_declared_index_clean.txt').write_text('declared\\n', encoding='utf-8')
(REPO / 'docs/badguys_batch1/scope_undeclared_index_clean.txt').write_text('undeclared\\n', encoding='utf-8')
"""

    write_patch_script(
        patch_path,
        files=["docs/badguys_batch1/scope_declared_index_clean.txt"],
        body=body,
    )

    argv = ctx.cfg.runner_cmd + [
        "--test-mode",
        ctx.cfg.issue_id,
        "badguys: scope undeclared leaves live tree unchanged",
        str(patch_path),
    ]

    snap: dict[str, list[str]] = {}

    def _snapshot_before() -> None:
        snap["before"] = _git_status_porcelain(ctx.repo_root)

    def _assert_unchanged_after() -> None:
        before = snap.get("before")
        if before is None:
            raise AssertionError("missing baseline snapshot")
        after = _git_status_porcelain(ctx.repo_root)
        if after != before:
            raise AssertionError(
                "expected live tree status unchanged by --test-mode run\n"
                f"before={before!r}\n"
                f"after={after!r}"
            )

    return Plan(
        steps=[
            FuncStep(name="snapshot_git_status_before", fn=_snapshot_before),
            CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=1),
            FuncStep(name="assert_git_status_unchanged_after", fn=_assert_unchanged_after),
        ],
        cleanup_paths=[patch_path],
    )


TEST = {
    "name": "test_065_scope_py_undeclared_leaves_index_clean",
    "makes_commit": False,
    "run": run,
}
