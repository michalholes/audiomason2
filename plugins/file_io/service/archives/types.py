"""Archive capability types for file_io.

All public strings and paths must be ASCII-safe in specifications and logs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ArchiveFormat(StrEnum):
    ZIP = "zip"
    TAR = "tar"
    TAR_GZ = "tar.gz"
    TAR_XZ = "tar.xz"
    RAR = "rar"
    SEVEN_Z = "7z"


class CollisionPolicy(StrEnum):
    ERROR = "error"
    RENAME = "rename"
    OVERWRITE = "overwrite"


class OpPhase(StrEnum):
    PLANNED = "planned"
    STARTED = "started"
    OK = "ok"
    ERROR = "error"


@dataclass(frozen=True)
class DetectedArchiveFormat:
    format: ArchiveFormat
    source: str  # 'suffix' | 'magic'
    confidence: float
    reason: str


@dataclass(frozen=True)
class OpEvent:
    op: str
    phase: OpPhase
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PackPlan:
    format: ArchiveFormat
    backend: str
    src_root: str
    src_dir: str
    dst_root: str
    dst_archive_path: str
    preserve_tree: bool
    flatten: bool
    collision: CollisionPolicy
    entries: list[str]
    collisions: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class UnpackPlan:
    format: ArchiveFormat
    backend: str
    src_root: str
    src_archive_path: str
    dst_root: str
    dst_dir: str
    preserve_tree: bool
    flatten: bool
    collision: CollisionPolicy
    entries: list[str]
    collisions: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class PackResult:
    format: ArchiveFormat
    backend: str
    dst_root: str
    dst_archive_path: str
    files_packed: int
    total_bytes: int
    is_deterministic: bool
    warnings: list[str]
    trace: list[OpEvent]


@dataclass(frozen=True)
class UnpackResult:
    format: ArchiveFormat
    backend: str
    dst_root: str
    dst_dir: str
    files_unpacked: int
    total_bytes: int
    warnings: list[str]
    trace: list[OpEvent]
