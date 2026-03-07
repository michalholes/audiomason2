from __future__ import annotations

import subprocess
from pathlib import Path


def resolve_repo_root(*, timeout_s: int = 0) -> Path:
    try:
        return Path(
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                check=True,
                text=True,
                capture_output=True,
                timeout=(int(timeout_s) if int(timeout_s) > 0 else None),
            ).stdout.strip()
        )
    except Exception:
        return Path.cwd()


def is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False
