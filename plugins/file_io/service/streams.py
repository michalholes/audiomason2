"""Streaming helpers for file_io.

The file service returns file handles for callers that need streaming I/O.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from .ops import AlreadyExistsError, IsADirectoryError, NotFoundError


@contextmanager
def open_read(path: Path) -> Iterator[BinaryIO]:
    """Open a file for reading in binary mode."""
    with open(path, "rb") as f:
        yield f


@contextmanager
def open_write(
    path: Path, *, overwrite: bool = False, mkdir_parents: bool = True
) -> Iterator[BinaryIO]:
    """Open a file for writing in binary mode."""
    if path.exists() and not overwrite:
        raise AlreadyExistsError(f"Destination exists: {path.name}")

    if mkdir_parents:
        path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "wb") as f:
        yield f


@contextmanager
def open_append(path: Path, *, mkdir_parents: bool = True) -> Iterator[BinaryIO]:
    """Open a file for append-only writing in binary mode."""
    if mkdir_parents:
        path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "ab") as f:
        yield f


def tail_bytes(path: Path, *, max_bytes: int) -> bytes:
    """Return the last max_bytes bytes from a file.

    This is a byte-level primitive (no decoding, no line parsing).
    """
    if max_bytes <= 0:
        raise ValueError("max_bytes must be > 0")

    if not path.exists():
        raise NotFoundError(f"Not found: {path.name}")
    if path.is_dir():
        raise IsADirectoryError(f"Is a directory: {path.name}")

    size = int(path.stat().st_size)
    start = max(0, size - max_bytes)

    with open(path, "rb") as f:
        f.seek(start)
        return f.read()
