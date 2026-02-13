"""File I/O capability service for AudioMason2.

This is a plugin-owned capability intended to be reused by UI layers and
pipeline steps. It is UI-agnostic.
"""

from __future__ import annotations

import time
import traceback
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO, Protocol, cast, runtime_checkable

from audiomason.core.config import ConfigResolver
from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus
from audiomason.core.logging import get_logger

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
from .streams import open_append, open_read, open_write
from .streams import tail_bytes as stream_tail_bytes
from .types import FileEntry, FileStat, RootName

_logger = get_logger(__name__)


def _short_traceback(*, max_lines: int = 20) -> str:
    tb_lines = traceback.format_exc().strip().splitlines()
    if len(tb_lines) <= max_lines:
        return "\n".join(tb_lines)
    return "\n".join(tb_lines[-max_lines:])


def _safe_publish(event: str, payload: dict[str, Any]) -> None:
    try:
        get_event_bus().publish(event, payload)
    except Exception:
        # Fail-safe: diagnostics emission must never crash processing.
        return


@contextmanager
def _observe_operation(
    *,
    operation: str,
    base: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    start = time.perf_counter()

    _safe_publish(
        "operation.start",
        build_envelope(
            event="operation.start",
            component="file_io",
            operation=operation,
            data=dict(base),
        ),
    )

    summary: dict[str, Any] = {}
    try:
        yield summary
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        end_data = dict(base)
        end_data.update(
            {
                "status": "failed",
                "duration_ms": duration_ms,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "traceback": _short_traceback(),
            }
        )
        _safe_publish(
            "operation.end",
            build_envelope(
                event="operation.end",
                component="file_io",
                operation=operation,
                data=end_data,
            ),
        )
        _logger.warning(
            f"{operation} status=failed duration_ms={duration_ms} "
            f"root={base.get('root')!r} rel_path={base.get('rel_path')!r}"
        )
        raise
    else:
        duration_ms = int((time.perf_counter() - start) * 1000)
        end_data = dict(base)
        end_data.update(summary)
        end_data.update({"status": "succeeded", "duration_ms": duration_ms})
        _safe_publish(
            "operation.end",
            build_envelope(
                event="operation.end",
                component="file_io",
                operation=operation,
                data=end_data,
            ),
        )
        # Summary logs are emitted on end only to avoid spam.
        summary_parts = [
            "status=succeeded",
            f"duration_ms={duration_ms}",
            f"root={base.get('root')!r}",
            f"rel_path={base.get('rel_path')!r}",
        ]
        if "resolved_path" in end_data:
            summary_parts.append(f"resolved_path={end_data.get('resolved_path')!r}")
        for k in ("items_count", "files_count", "dirs_count", "deleted", "bytes"):
            if k in end_data:
                summary_parts.append(f"{k}={end_data[k]!r}")
        _logger.info(f"{operation} " + " ".join(summary_parts))


@runtime_checkable
class _SupportsReadinto(Protocol):
    def readinto(self, b: bytearray | memoryview) -> int: ...


class _CountingBinaryIO:
    def __init__(self, raw: BinaryIO) -> None:
        self._raw = raw
        self.bytes_read = 0
        self.bytes_written = 0

    def read(self, size: int = -1) -> bytes:
        data = self._raw.read(size)
        if data:
            self.bytes_read += len(data)
        return data

    def readline(self, size: int = -1) -> bytes:
        data = self._raw.readline(size)
        if data:
            self.bytes_read += len(data)
        return data

    def readinto(self, b: bytearray | memoryview) -> int:
        raw = self._raw
        if isinstance(raw, _SupportsReadinto):
            n = raw.readinto(b)
        else:
            data = raw.read(len(b))
            if data:
                b[: len(data)] = data
                n = len(data)
            else:
                n = 0
        if n:
            self.bytes_read += int(n)
        return int(n)

    def write(self, b: bytes | bytearray | memoryview) -> int:
        n = self._raw.write(b)
        if n is None:
            n = len(b)
        self.bytes_written += int(n)
        return int(n)

    def writelines(self, lines: Iterable[bytes]) -> None:
        for line in lines:
            self.write(line)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._raw, name)


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
        - file_io.roots.config_dir
        - file_io.roots.wizards_dir

        Legacy fallback keys:
        - inbox_dir, stage_dir, outbox_dir, config_dir, wizards_dir
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
        config_dir = Path(
            _get("file_io.roots.config_dir", "config_dir", default="/tmp/audiomason/config")
        )
        wizards_dir = Path(
            _get("file_io.roots.wizards_dir", "wizards_dir", default="/tmp/audiomason/wizards")
        )

        roots = {
            RootName.INBOX: inbox_dir.expanduser(),
            RootName.STAGE: stage_dir.expanduser(),
            RootName.JOBS: jobs_dir.expanduser(),
            RootName.OUTBOX: outbox_dir.expanduser(),
            RootName.CONFIG: config_dir.expanduser(),
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
        abs_path = resolve_path(self._root(root).dir_path, rel_path, root_name=root)
        base = {"root": root.value, "rel_path": rel_path, "resolved_path": str(abs_path)}
        with _observe_operation(operation="file_io.resolve", base=base):
            return abs_path

    def list_dir(
        self, root: RootName, rel_path: str = ".", *, recursive: bool = False
    ) -> list[FileEntry]:
        abs_path = resolve_path(self._root(root).dir_path, rel_path, root_name=root)
        base = {
            "root": root.value,
            "rel_path": rel_path,
            "resolved_path": str(abs_path),
            "recursive": bool(recursive),
        }
        with _observe_operation(operation="file_io.list", base=base) as summary:
            entries = op_list_dir(self._root(root), rel_path, recursive=recursive)
            summary["items_count"] = len(entries)
            summary["files_count"] = sum(1 for e in entries if not e.is_dir)
            summary["dirs_count"] = sum(1 for e in entries if e.is_dir)
            return entries

    def stat(self, root: RootName, rel_path: str) -> FileStat:
        abs_path = resolve_path(self._root(root).dir_path, rel_path, root_name=root)
        base = {"root": root.value, "rel_path": rel_path, "resolved_path": str(abs_path)}
        with _observe_operation(operation="file_io.stat", base=base):
            return op_stat(self._root(root), rel_path)

    def exists(self, root: RootName, rel_path: str) -> bool:
        abs_path = resolve_path(self._root(root).dir_path, rel_path, root_name=root)
        base = {"root": root.value, "rel_path": rel_path, "resolved_path": str(abs_path)}
        with _observe_operation(operation="file_io.exists", base=base):
            return op_exists(self._root(root), rel_path)

    def mkdir(
        self, root: RootName, rel_path: str, *, parents: bool = True, exist_ok: bool = True
    ) -> None:
        abs_path = resolve_path(self._root(root).dir_path, rel_path, root_name=root)
        base = {
            "root": root.value,
            "rel_path": rel_path,
            "resolved_path": str(abs_path),
            "parents": bool(parents),
            "exist_ok": bool(exist_ok),
        }
        with _observe_operation(operation="file_io.mkdir", base=base):
            op_mkdir(self._root(root), rel_path, parents=parents, exist_ok=exist_ok)

    def rename(self, root: RootName, src: str, dst: str, *, overwrite: bool = False) -> None:
        src_abs = resolve_path(self._root(root).dir_path, src, root_name=root)
        dst_abs = resolve_path(self._root(root).dir_path, dst, root_name=root)
        base = {
            "root": root.value,
            "rel_path": src,
            "src": src,
            "dst": dst,
            "resolved_path": str(src_abs),
            "resolved_dst_path": str(dst_abs),
            "overwrite": bool(overwrite),
        }
        with _observe_operation(operation="file_io.rename", base=base):
            op_rename(self._root(root), src, dst, overwrite=overwrite)

    def delete_file(self, root: RootName, rel_path: str) -> None:
        abs_path = resolve_path(self._root(root).dir_path, rel_path, root_name=root)
        base = {"root": root.value, "rel_path": rel_path, "resolved_path": str(abs_path)}
        with _observe_operation(operation="file_io.delete", base=base) as summary:
            op_delete_file(self._root(root), rel_path)
            summary["deleted"] = True

    def rmdir(self, root: RootName, rel_path: str) -> None:
        abs_path = resolve_path(self._root(root).dir_path, rel_path, root_name=root)
        base = {"root": root.value, "rel_path": rel_path, "resolved_path": str(abs_path)}
        with _observe_operation(operation="file_io.rmdir", base=base):
            op_rmdir(self._root(root), rel_path)

    def rmtree(self, root: RootName, rel_path: str) -> None:
        abs_path = resolve_path(self._root(root).dir_path, rel_path, root_name=root)
        base = {"root": root.value, "rel_path": rel_path, "resolved_path": str(abs_path)}
        with _observe_operation(operation="file_io.rmtree", base=base):
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
        src_abs = resolve_path(self._root(root).dir_path, src, root_name=root)
        dst_abs = resolve_path(self._root(root).dir_path, dst, root_name=root)
        base = {
            "root": root.value,
            "rel_path": src,
            "src": src,
            "dst": dst,
            "resolved_path": str(src_abs),
            "resolved_dst_path": str(dst_abs),
            "overwrite": bool(overwrite),
            "mkdir_parents": bool(mkdir_parents),
        }
        with _observe_operation(operation="file_io.copy", base=base):
            op_copy(
                self._root(root),
                src,
                dst,
                overwrite=overwrite,
                mkdir_parents=mkdir_parents,
            )

    def checksum(self, root: RootName, rel_path: str, *, algo: str = "sha256") -> str:
        abs_path = resolve_path(self._root(root).dir_path, rel_path, root_name=root)
        base = {
            "root": root.value,
            "rel_path": rel_path,
            "resolved_path": str(abs_path),
            "algo": str(algo),
        }
        with _observe_operation(operation="file_io.checksum", base=base):
            if algo != "sha256":
                raise ValueError("Only sha256 is supported")
            return checksums.sha256(abs_path)

    def tail_bytes(self, root: RootName, rel_path: str, *, max_bytes: int) -> bytes:
        abs_path = resolve_path(self._root(root).dir_path, rel_path, root_name=root)
        base = {
            "root": root.value,
            "rel_path": rel_path,
            "resolved_path": str(abs_path),
            "max_bytes": int(max_bytes),
        }
        with _observe_operation(operation="file_io.tail_bytes", base=base) as summary:
            data = stream_tail_bytes(abs_path, max_bytes=max_bytes)
            summary["bytes"] = len(data)
            return data

    @contextmanager
    def open_read(self, root: RootName, rel_path: str) -> Iterator[BinaryIO]:
        abs_path = resolve_path(self._root(root).dir_path, rel_path, root_name=root)
        base = {"root": root.value, "rel_path": rel_path, "resolved_path": str(abs_path)}
        with (
            _observe_operation(operation="file_io.open_read", base=base) as summary,
            open_read(abs_path) as f_raw,
        ):
            f = _CountingBinaryIO(f_raw)
            try:
                yield cast(BinaryIO, f)
            finally:
                summary["bytes"] = int(f.bytes_read)

    @contextmanager
    def open_write(
        self,
        root: RootName,
        rel_path: str,
        *,
        overwrite: bool = False,
        mkdir_parents: bool = True,
    ) -> Iterator[BinaryIO]:
        abs_path = resolve_path(self._root(root).dir_path, rel_path, root_name=root)
        base = {
            "root": root.value,
            "rel_path": rel_path,
            "resolved_path": str(abs_path),
            "overwrite": bool(overwrite),
            "mkdir_parents": bool(mkdir_parents),
        }
        with (
            _observe_operation(operation="file_io.open_write", base=base) as summary,
            open_write(abs_path, overwrite=overwrite, mkdir_parents=mkdir_parents) as f_raw,
        ):
            f = _CountingBinaryIO(f_raw)
            try:
                yield cast(BinaryIO, f)
            finally:
                summary["bytes"] = int(f.bytes_written)

    @contextmanager
    def open_append(
        self, root: RootName, rel_path: str, *, mkdir_parents: bool = True
    ) -> Iterator[BinaryIO]:
        abs_path = resolve_path(self._root(root).dir_path, rel_path, root_name=root)
        base = {
            "root": root.value,
            "rel_path": rel_path,
            "resolved_path": str(abs_path),
            "mkdir_parents": bool(mkdir_parents),
        }
        with (
            _observe_operation(operation="file_io.open_append", base=base) as summary,
            open_append(abs_path, mkdir_parents=mkdir_parents) as f_raw,
        ):
            f = _CountingBinaryIO(f_raw)
            try:
                yield cast(BinaryIO, f)
            finally:
                summary["bytes"] = int(f.bytes_written)
