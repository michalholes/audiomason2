from __future__ import annotations

from pathlib import Path


def find_repo_root() -> Path:
    cwd = Path.cwd().resolve()
    # common: run from repo root
    if (cwd / "plugins").is_dir():
        return cwd
    # allow running from inside plugins/web_interface
    for parent in [cwd, *cwd.parents]:
        if (parent / "plugins").is_dir():
            return parent
    return cwd
