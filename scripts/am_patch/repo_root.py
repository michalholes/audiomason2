from __future__ import annotations

from pathlib import Path


def resolve_repo_root() -> Path:
    import subprocess

    p = subprocess.run(["git", "rev-parse", "--show-toplevel"], text=True, capture_output=True)
    if p.returncode == 0 and p.stdout.strip():
        return Path(p.stdout.strip())
    return Path.cwd()


def is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False
