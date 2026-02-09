"""Types for file_io service.

ASCII-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RootName(StrEnum):
    """Named root namespaces for file operations."""

    INBOX = "inbox"
    STAGE = "stage"
    JOBS = "jobs"
    OUTBOX = "outbox"
    CONFIG = "config"
    WIZARDS = "wizards"


@dataclass(frozen=True)
class FileEntry:
    """Directory entry returned by list_dir."""

    rel_path: str
    is_dir: bool
    size: int | None
    mtime: float | None


@dataclass(frozen=True)
class FileStat:
    """Metadata returned by stat."""

    rel_path: str
    is_dir: bool
    size: int
    mtime: float
