from __future__ import annotations

import subprocess
from pathlib import Path

from badguys._util import CmdStep, FuncStep, Plan, write_patch_script


def _git_names(repo_root: Path, args: list[str]) -> list[str]:
    cp = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    out = (cp.stdout or "").strip()
    if not out:
        return []
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def run(ctx) -> Plan:
    patch_dir = ctx.cfg.patches_dir
    patch_dir.mkdir(parents=True, exist_ok=True)

    patch_path = patch_dir / f"issue_{ctx.cfg.issue_id}__bg_scope_undeclared_index_clean.py"

    body = """
(REPO / 'docs/badguys_batch1/scope_declared_index_clean.txt').parent.mkdir(parents=True, exist_ok=True)
(REPO / 'docs/badguys_batch1/scope_declared_index_clean.txt').write_text('declared\n', encoding='utf-8')
(REPO / 'docs/badguys_batch1/scope_undeclared_index_clean.txt').write_text('undeclared\n', encoding='utf-8')
"""

    write_patch_script(
        patch_path,
        files=["docs/badguys_batch1/scope_declared_index_clean.txt"],
        body=body,
    )

    argv = ctx.cfg.runner_cmd + [
        "--test-mode",
        ctx.cfg.issue_id,
        "badguys: scope undeclared leaves index clean",
        str(patch_path),
    ]

    def _assert_git_clean() -> None:
        cached = _git_names(ctx.repo_root, ["diff", "--cached", "--name-only"])
        if cached:
            raise AssertionError(f"expected empty git index, got: {cached!r}")
        wt = _git_names(ctx.repo_root, ["diff", "--name-only"])
        if wt:
            raise AssertionError(f"expected clean worktree, got: {wt!r}")

    return Plan(
        steps=[
            CmdStep(argv=argv, cwd=ctx.repo_root, expect_rc=1),
            FuncStep(name="assert_git_index_clean", fn=_assert_git_clean),
        ],
        cleanup_paths=[patch_path],
    )


TEST = {
    "name": "test_065_scope_py_undeclared_leaves_index_clean",
    "makes_commit": False,
    "run": run,
}
