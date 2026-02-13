from __future__ import annotations

from pathlib import Path

from am_patch.workspace import create_workspace, workspace_path


def test_workspace_path_is_deterministic(repo_root: Path, fake_deps) -> None:
    p = workspace_path(repo_root, "802")
    assert p == repo_root / ".am_patch_workspaces" / "issue_802"


def test_create_workspace_copies_repo_but_excludes_git(repo_root: Path, fake_deps) -> None:
    ws = create_workspace(repo_root, "802", fake_deps, update=False)
    assert ws.path.exists()
    assert (ws.path / "x.txt").read_text(encoding="utf-8") == "one\n"

    # Ensure workspace does not contain .git.
    assert not (ws.path / ".git").exists()

    # Ensure recursive workspace nesting is excluded.
    (repo_root / ".am_patch_workspaces").mkdir(exist_ok=True)
    (repo_root / ".am_patch_workspaces" / "sentinel").write_text("x", encoding="utf-8")
    ws2 = create_workspace(repo_root, "802", fake_deps, update=False)
    assert not (ws2.path / ".am_patch_workspaces").exists()
