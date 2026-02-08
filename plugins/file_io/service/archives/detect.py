"""Archive format detection for file_io.

Detection is only performed when explicitly requested by higher layers.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import BinaryIO

from .types import ArchiveFormat, DetectedArchiveFormat

_SUFFIX_MAP: list[tuple[str, ArchiveFormat]] = [
    (".tar.gz", ArchiveFormat.TAR_GZ),
    (".tgz", ArchiveFormat.TAR_GZ),
    (".tar.xz", ArchiveFormat.TAR_XZ),
    (".txz", ArchiveFormat.TAR_XZ),
    (".tar", ArchiveFormat.TAR),
    (".zip", ArchiveFormat.ZIP),
    (".rar", ArchiveFormat.RAR),
    (".7z", ArchiveFormat.SEVEN_Z),
]


def detect_from_suffix(path: Path) -> DetectedArchiveFormat | None:
    name = path.name.lower()
    for suffix, fmt in _SUFFIX_MAP:
        if name.endswith(suffix):
            return DetectedArchiveFormat(
                format=fmt,
                source="suffix",
                confidence=1.0,
                reason=f"Matched suffix: {suffix}",
            )
    return None


def _read_prefix(stream: BinaryIO, n: int = 32) -> bytes:
    pos = stream.tell()
    try:
        data = stream.read(n)
    finally:
        with contextlib.suppress(Exception):
            stream.seek(pos)
    return data


def detect_from_magic(stream: BinaryIO) -> DetectedArchiveFormat | None:
    data = _read_prefix(stream, 64)

    # ZIP: PK\x03\x04 (local file header)
    if data.startswith(b"PK\x03\x04"):
        return DetectedArchiveFormat(
            format=ArchiveFormat.ZIP,
            source="magic",
            confidence=1.0,
            reason="ZIP magic PK\\x03\\x04",
        )

    # RAR4: Rar!\x1A\x07\x00, RAR5: Rar!\x1A\x07\x01\x00
    if data.startswith(b"Rar!\x1a\x07\x00") or data.startswith(b"Rar!\x1a\x07\x01\x00"):
        return DetectedArchiveFormat(
            format=ArchiveFormat.RAR, source="magic", confidence=1.0, reason="RAR magic"
        )

    # 7z: 37 7A BC AF 27 1C
    if data.startswith(b"7z\xbc\xaf\x27\x1c"):
        return DetectedArchiveFormat(
            format=ArchiveFormat.SEVEN_Z, source="magic", confidence=1.0, reason="7Z magic"
        )

    # GZ: 1F 8B
    if data.startswith(b"\x1f\x8b"):
        return DetectedArchiveFormat(
            format=ArchiveFormat.TAR_GZ,
            source="magic",
            confidence=0.7,
            reason="GZ magic (assume tar.gz when requested as archive)",
        )

    # XZ: FD 37 7A 58 5A 00
    if data.startswith(b"\xfd7zXZ\x00"):
        return DetectedArchiveFormat(
            format=ArchiveFormat.TAR_XZ,
            source="magic",
            confidence=0.7,
            reason="XZ magic (assume tar.xz when requested as archive)",
        )

    return None
