"""File I/O capability service for AudioMason2.

This is a plugin-owned capability intended to be reused by UI layers and
pipeline steps. It is UI-agnostic.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from audiomason.core.config import ConfigResolver

from . import checksums
from .ops import copy as op_copy
from .ops import delete_file as op_delete_file
from .ops import exists as op_exists
from .ops import list_dir as op_list_dir
from .ops import mkdir as op_mkdir
from .ops import rename as op_rename
from .ops import rmdir as op_rmdir
from .ops import rmtree as op_rmtree
from .ops import stat_path as op_stat
from .paths import RootConfig, resolve_path
from .streams import open_read, open_write
from .types import FileEntry, FileStat, RootName


class FileService:
    """File I/O capability.

    File operations are scoped to configured roots.
    """

    def __init__(self, roots: dict[RootName, Path]) -> None:
        self._roots = {k: RootConfig(name=k, dir_path=v) for k, v in roots.items()}

    @classmethod
    def from_resolver(cls, resolver: ConfigResolver) -> FileService:
        """Build FileService from ConfigResolver.

        Configuration keys (preferred):
        - file_io.roots.inbox_dir
        - file_io.roots.stage_dir
        - file_io.roots.jobs_dir
        - file_io.roots.outbox_dir
        - file_io.roots.wizards_dir

        Legacy fallback keys:
        - inbox_dir, stage_dir, outbox_dir, wizards_dir
        - output_dir (used as fallback for outbox_dir)
        """

        def _get(key: str, fallback_key: str | None = None, default: str | None = None) -> str:
            try:
                val, _src = resolver.resolve(key)
                if isinstance(val, str) and val:
                    return val
            except Exception:
                pass

            if fallback_key is not None:
                try:
                    val, _src = resolver.resolve(fallback_key)
                    if isinstance(val, str) and val:
                        return val
                except Exception:
                    pass

            if default is not None:
                return default

            raise ValueError(f"Missing configuration key: {key}")

        inbox_dir = Path(_get("file_io.roots.inbox_dir", "inbox_dir"))
        stage_dir = Path(_get("file_io.roots.stage_dir", "stage_dir"))
        jobs_dir = Path(_get("file_io.roots.jobs_dir", default="/tmp/audiomason/jobs"))
        outbox_dir = Path(_get("file_io.roots.outbox_dir", "outbox_dir", _get("output_dir")))
        wizards_dir = Path(
            _get("file_io.roots.wizards_dir", "wizards_dir", default="/tmp/audiomason/wizards")
        )

        roots = {
            RootName.INBOX: inbox_dir.expanduser(),
            RootName.STAGE: stage_dir.expanduser(),
            RootName.JOBS: jobs_dir.expanduser(),
            RootName.OUTBOX: outbox_dir.expanduser(),
            RootName.WIZARDS: wizards_dir.expanduser(),
        }

        # Ensure roots exist.
        for p in roots.values():
            p.mkdir(parents=True, exist_ok=True)

        return cls(roots)

    def _root(self, root: RootName) -> RootConfig:
        if root not in self._roots:
            raise ValueError(f"Unknown root: {root}")
        return self._roots[root]

    def root_dir(self, root: RootName) -> Path:
        """Return the configured absolute directory for a root."""
        return self._root(root).dir_path

    def resolve_abs_path(self, root: RootName, rel_path: str) -> Path:
        """Resolve a relative path to an absolute path under a root."""
        return resolve_path(self._root(root).dir_path, rel_path)

    def list_dir(
        self, root: RootName, rel_path: str = ".", *, recursive: bool = False
    ) -> list[FileEntry]:
        return op_list_dir(self._root(root), rel_path, recursive=recursive)

    def stat(self, root: RootName, rel_path: str) -> FileStat:
        return op_stat(self._root(root), rel_path)

    def exists(self, root: RootName, rel_path: str) -> bool:
        return op_exists(self._root(root), rel_path)

    def mkdir(
        self, root: RootName, rel_path: str, *, parents: bool = True, exist_ok: bool = True
    ) -> None:
        op_mkdir(self._root(root), rel_path, parents=parents, exist_ok=exist_ok)

    def rename(self, root: RootName, src: str, dst: str, *, overwrite: bool = False) -> None:
        op_rename(self._root(root), src, dst, overwrite=overwrite)

    def delete_file(self, root: RootName, rel_path: str) -> None:
        op_delete_file(self._root(root), rel_path)

    def rmdir(self, root: RootName, rel_path: str) -> None:
        op_rmdir(self._root(root), rel_path)

    def rmtree(self, root: RootName, rel_path: str) -> None:
        op_rmtree(self._root(root), rel_path)

    def copy(
        self,
        root: RootName,
        src: str,
        dst: str,
        *,
        overwrite: bool = False,
        mkdir_parents: bool = True,
    ) -> None:
        op_copy(self._root(root), src, dst, overwrite=overwrite, mkdir_parents=mkdir_parents)

    def checksum(self, root: RootName, rel_path: str, *, algo: str = "sha256") -> str:
        abs_path = resolve_path(self._root(root).dir_path, rel_path)
        if algo != "sha256":
            raise ValueError("Only sha256 is supported")
        return checksums.sha256(abs_path)

    @contextmanager
    def open_read(self, root: RootName, rel_path: str) -> Iterator[BinaryIO]:
        abs_path = resolve_path(self._root(root).dir_path, rel_path)
        with open_read(abs_path) as f:
            yield f

    @contextmanager
    def open_write(
        self,
        root: RootName,
        rel_path: str,
        *,
        overwrite: bool = False,
        mkdir_parents: bool = True,
    ) -> Iterator[BinaryIO]:
        abs_path = resolve_path(self._root(root).dir_path, rel_path)
        with open_write(abs_path, overwrite=overwrite, mkdir_parents=mkdir_parents) as f:
            yield f
