from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .deps import Deps


@dataclass(frozen=True)
class Workspace:
    path: Path
    existed: bool


def workspace_path(repo_root: Path, issue_id: str | None) -> Path:
    iid = issue_id or "unknown"
    return repo_root / ".am_patch_workspaces" / f"issue_{iid}"


def create_workspace(repo_root: Path, issue_id: str | None, deps: Deps, *, update: bool) -> Workspace:
    ws_root = workspace_path(repo_root, issue_id)
    ws_repo = ws_root / "repo"

    existed = deps.fs.exists(ws_root)
    if existed:
        deps.fs.rmtree(ws_root)
        existed = False

    deps.fs.mkdir(ws_root)

    def _ignore(_dir: str, names: list[str]) -> set[str]:
        # Prevent recursive workspace nesting and avoid copying git metadata.
        ignore: set[str] = set()
        for n in names:
            if n in {".am_patch_workspaces", ".git"}:
                ignore.add(n)
        return ignore

    shutil.copytree(repo_root, ws_repo, ignore=_ignore, dirs_exist_ok=False)
    return Workspace(path=ws_repo, existed=existed)


def cleanup_workspace(ws_repo: Path, deps: Deps) -> None:
    deps.fs.rmtree(ws_repo.parent)
