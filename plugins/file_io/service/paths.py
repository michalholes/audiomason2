"""Path normalization and root-jail resolution for file_io.

All paths are relative to a configured root directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from audiomason.core.errors import FileError

from .types import RootName


class PathOutsideRootError(FileError):
    """Raised when a requested path escapes the configured root."""


class InvalidRelativePathError(FileError):
    """Raised when a requested relative path is invalid."""


@dataclass(frozen=True)
class RootConfig:
    """Resolved root directory on disk."""

    name: RootName
    dir_path: Path


def normalize_rel_path(rel_path: str) -> PurePosixPath:
    """Normalize and validate a relative path.

    Rules:
    - must be relative (no leading slash)
    - no '..' segments
    - backslashes are treated as separators

    Returns:
        PurePosixPath for normalized relative path

    Raises:
        InvalidRelativePathError
    """
    if rel_path is None:
        raise InvalidRelativePathError("Path is required")

    # Normalize separators for consistent behavior across clients.
    rel_path = str(rel_path).replace("\\", "/")

    p = PurePosixPath(rel_path)

    if p.is_absolute():
        raise InvalidRelativePathError("Absolute paths are not allowed")

    parts = p.parts
    if any(part == ".." for part in parts):
        raise InvalidRelativePathError("Parent path segments ('..') are not allowed")

    # PurePosixPath('.') is valid and represents the root itself.
    return p


def resolve_path(root_dir: Path, rel_path: str) -> Path:
    """Resolve a relative path within a root directory.

    Raises:
        PathOutsideRootError
        InvalidRelativePathError
    """
    rel = normalize_rel_path(rel_path)

    abs_path = (root_dir / Path(*rel.parts)).resolve()
    root_resolved = root_dir.resolve()

    # Ensure abs_path is inside root_dir.
    try:
        abs_path.relative_to(root_resolved)
    except ValueError:
        raise PathOutsideRootError("Path escapes configured root") from None

    return abs_path
