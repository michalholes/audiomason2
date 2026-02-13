from __future__ import annotations

import shutil
from pathlib import Path

from .deps import Deps
from .model import RunnerError


def promote_from_workspace(ws_repo: Path, repo_root: Path, deps: Deps, changed_paths: tuple[str, ...]) -> None:
    for rel in changed_paths:
        src = ws_repo / rel
        dst = repo_root / rel

        if not src.exists():
            raise RunnerError(f"Promote source missing: {rel}")

        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
