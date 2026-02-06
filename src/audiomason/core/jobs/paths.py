from __future__ import annotations

from pathlib import Path


def jobs_root() -> Path:
    return Path.home() / ".audiomason" / "jobs"
