"""Filesystem operations for file_io service.

This module is UI-agnostic and operates within configured root directories.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from audiomason.core.errors import FileError

from .paths import RootConfig, resolve_path
from .types import FileEntry, FileStat


class NotFoundError(FileError):
    """Raised when a file or directory is not found."""


class AlreadyExistsError(FileError):
    """Raised when a destination already exists and overwrite is disabled."""


class NotADirectoryError(FileError):
    """Raised when a directory was expected."""


class IsADirectoryError(FileError):
    """Raised when a file was expected."""


def list_dir(root: RootConfig, rel_path: str, *, recursive: bool = False) -> list[FileEntry]:
    """List directory entries under rel_path.

    Ordering is stable and deterministic: lexicographic by rel_path.
    """
    base = resolve_path(root.dir_path, rel_path)

    if not base.exists():
        raise NotFoundError(f"Not found: {rel_path}")
    if not base.is_dir():
        raise NotADirectoryError(f"Not a directory: {rel_path}")

    entries: list[FileEntry] = []

    if recursive:
        for item in sorted(base.rglob("*")):
            rel = item.relative_to(root.dir_path).as_posix()
            st = item.stat()
            entries.append(
                FileEntry(
                    rel_path=rel,
                    is_dir=item.is_dir(),
                    size=None if item.is_dir() else int(st.st_size),
                    mtime=float(st.st_mtime),
                )
            )
    else:
        for item in sorted(base.iterdir(), key=lambda p: p.name):
            rel = item.relative_to(root.dir_path).as_posix()
            st = item.stat()
            entries.append(
                FileEntry(
                    rel_path=rel,
                    is_dir=item.is_dir(),
                    size=None if item.is_dir() else int(st.st_size),
                    mtime=float(st.st_mtime),
                )
            )

    # Ensure stable sort by rel_path across platforms.
    entries.sort(key=lambda e: e.rel_path)
    return entries


def stat_path(root: RootConfig, rel_path: str) -> FileStat:
    abs_path = resolve_path(root.dir_path, rel_path)
    if not abs_path.exists():
        raise NotFoundError(f"Not found: {rel_path}")
    st = abs_path.stat()
    return FileStat(
        rel_path=abs_path.relative_to(root.dir_path).as_posix(),
        is_dir=abs_path.is_dir(),
        size=int(st.st_size),
        mtime=float(st.st_mtime),
    )


def exists(root: RootConfig, rel_path: str) -> bool:
    abs_path = resolve_path(root.dir_path, rel_path)
    return abs_path.exists()


def mkdir(root: RootConfig, rel_path: str, *, parents: bool = True, exist_ok: bool = True) -> None:
    abs_path = resolve_path(root.dir_path, rel_path)
    abs_path.mkdir(parents=parents, exist_ok=exist_ok)


def rename(
    root: RootConfig,
    src: str,
    dst: str,
    *,
    overwrite: bool = False,
) -> None:
    src_path = resolve_path(root.dir_path, src)
    dst_path = resolve_path(root.dir_path, dst)

    if not src_path.exists():
        raise NotFoundError(f"Not found: {src}")

    if dst_path.exists() and not overwrite:
        raise AlreadyExistsError(f"Destination exists: {dst}")

    dst_path.parent.mkdir(parents=True, exist_ok=True)

    if dst_path.exists() and overwrite:
        if dst_path.is_dir():
            shutil.rmtree(dst_path)
        else:
            dst_path.unlink()

    src_path.rename(dst_path)


def delete_file(root: RootConfig, rel_path: str) -> None:
    abs_path = resolve_path(root.dir_path, rel_path)
    if not abs_path.exists():
        raise NotFoundError(f"Not found: {rel_path}")
    if abs_path.is_dir():
        raise IsADirectoryError(f"Is a directory: {rel_path}")
    abs_path.unlink()


def rmdir(root: RootConfig, rel_path: str) -> None:
    abs_path = resolve_path(root.dir_path, rel_path)
    if not abs_path.exists():
        raise NotFoundError(f"Not found: {rel_path}")
    abs_path.rmdir()


def rmtree(root: RootConfig, rel_path: str) -> None:
    abs_path = resolve_path(root.dir_path, rel_path)
    if not abs_path.exists():
        raise NotFoundError(f"Not found: {rel_path}")
    if abs_path.is_file():
        abs_path.unlink()
    else:
        shutil.rmtree(abs_path)


def copy(
    root: RootConfig,
    src: str,
    dst: str,
    *,
    overwrite: bool = False,
    mkdir_parents: bool = True,
) -> None:
    src_path = resolve_path(root.dir_path, src)
    dst_path = resolve_path(root.dir_path, dst)

    if not src_path.exists():
        raise NotFoundError(f"Not found: {src}")
    if src_path.is_dir():
        raise IsADirectoryError(f"Is a directory: {src}")

    if dst_path.exists() and not overwrite:
        raise AlreadyExistsError(f"Destination exists: {dst}")

    if mkdir_parents:
        dst_path.parent.mkdir(parents=True, exist_ok=True)

    if dst_path.exists() and overwrite:
        if dst_path.is_dir():
            shutil.rmtree(dst_path)
        else:
            dst_path.unlink()

    shutil.copy2(src_path, dst_path)


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def atomic_write_bytes(path: Path, data: bytes, *, overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise AlreadyExistsError(f"Destination exists: {path.name}")

    ensure_parent_dir(path)

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())

    tmp_path.replace(path)
