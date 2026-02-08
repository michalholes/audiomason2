"""Checksum helpers for file_io."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .ops import IsADirectoryError, NotFoundError


def sha256(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Compute SHA256 checksum for a file and return hex string."""
    if not path.exists():
        raise NotFoundError(f"Not found: {path.name}")
    if path.is_dir():
        raise IsADirectoryError(f"Is a directory: {path.name}")

    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)

    return h.hexdigest()
