"""Archive capability service for file_io.

This module provides pack/unpack helpers scoped to FileService roots.

Autodetection is performed only when explicitly requested.
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import tarfile
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Literal, cast

from audiomason.core.config import ConfigResolver
from audiomason.core.errors import FileError
from audiomason.core.logging import get_logger

from ..service import FileService
from ..types import RootName
from .detect import detect_from_magic, detect_from_suffix
from .types import (
    ArchiveFormat,
    CollisionPolicy,
    DetectedArchiveFormat,
    OpEvent,
    OpPhase,
    PackPlan,
    PackResult,
    UnpackPlan,
    UnpackResult,
)

log = get_logger(__name__)


TarReadMode = Literal["r:", "r:gz", "r:xz"]
TarWriteMode = Literal["w:", "w:gz", "w:xz"]


def _bool_from_resolver(resolver: ConfigResolver, key: str, default: bool) -> bool:
    try:
        val, _src = resolver.resolve(key)
    except Exception:
        return default
    return bool(val)


def _str_from_resolver(resolver: ConfigResolver, key: str, default: str) -> str:
    try:
        val, _src = resolver.resolve(key)
    except Exception:
        return default
    return str(val)


def _collision_from_resolver(
    resolver: ConfigResolver, key: str, default: CollisionPolicy
) -> CollisionPolicy:
    val = _str_from_resolver(resolver, key, default.value).lower()
    for p in CollisionPolicy:
        if p.value == val:
            return p
    return default


def _stable_sorted(items: Iterable[str]) -> list[str]:
    return sorted(items)


def _apply_flatten(name: str) -> str:
    return Path(name).name


def _rename_for_collision(existing: set[str], name: str) -> str:
    base = name
    stem = Path(base).stem
    suffix = Path(base).suffix
    if suffix:
        head = f"{stem}"
        tail = suffix
    else:
        head = base
        tail = ""
    i = 1
    candidate = base
    while candidate in existing:
        candidate = f"{head}__{i}{tail}"
        i += 1
    return candidate


def _zipinfo_deterministic(name: str) -> zipfile.ZipInfo:
    zi = zipfile.ZipInfo(filename=name)
    zi.date_time = (1980, 1, 1, 0, 0, 0)
    zi.compress_type = zipfile.ZIP_DEFLATED
    return zi


def _tarinfo_deterministic(name: str, size: int) -> tarfile.TarInfo:
    ti = tarfile.TarInfo(name=name)
    ti.size = size
    ti.mtime = 0
    ti.uid = 0
    ti.gid = 0
    ti.uname = ""
    ti.gname = ""
    ti.mode = 0o644
    return ti


class ArchiveService:
    """Archive capability.

    This service is intentionally thin; decisions remain with higher layers.
    """

    def __init__(self, file_service: FileService, resolver: ConfigResolver | None = None) -> None:
        self._fs = file_service
        self._resolver = resolver or ConfigResolver(cli_args={})

    def detect_format(self, root: RootName, rel_path: str) -> DetectedArchiveFormat:
        abs_path = self._fs.resolve_abs_path(root, rel_path)
        detected = detect_from_suffix(abs_path)
        if detected is not None:
            return detected

        with self._fs.open_read(root, rel_path) as f:
            magic = detect_from_magic(f)
        if magic is not None:
            return magic

        raise FileError("Unable to detect archive format; specify fmt explicitly")

    def plan_unpack(
        self,
        src_root: RootName,
        src_archive_path: str,
        dst_root: RootName,
        dst_dir: str,
        *,
        fmt: ArchiveFormat | None = None,
        autodetect: bool = False,
        preserve_tree: bool = True,
        flatten: bool = False,
        collision: CollisionPolicy | None = None,
        allow_external: bool | None = None,
        debug: bool = False,
    ) -> UnpackPlan:
        _collision = collision or _collision_from_resolver(
            self._resolver, "file_io.archives.flatten.collision", CollisionPolicy.ERROR
        )
        _allow_external = allow_external
        if _allow_external is None:
            _allow_external = _bool_from_resolver(
                self._resolver, "file_io.archives.allow_external", True
            )

        _fmt = self._resolve_format(src_root, src_archive_path, fmt=fmt, autodetect=autodetect)

        backend = self._select_backend_for_unpack(_fmt, allow_external=_allow_external)

        entries, warnings = self._list_entries_for_plan(src_root, src_archive_path, _fmt, backend)

        mapped, collisions = self._map_entry_names(
            entries, preserve_tree=preserve_tree, flatten=flatten, collision=_collision
        )

        if debug:
            log.debug(
                f"plan_unpack format={_fmt} backend={backend} entries={len(entries)} "
                f"collisions={len(collisions)}"
            )

        return UnpackPlan(
            format=_fmt,
            backend=backend,
            src_root=src_root.value,
            src_archive_path=src_archive_path,
            dst_root=dst_root.value,
            dst_dir=dst_dir,
            preserve_tree=preserve_tree,
            flatten=flatten,
            collision=_collision,
            entries=mapped,
            collisions=collisions,
            warnings=warnings,
        )

    def unpack(
        self,
        src_root: RootName,
        src_archive_path: str,
        dst_root: RootName,
        dst_dir: str,
        *,
        fmt: ArchiveFormat | None = None,
        autodetect: bool = False,
        preserve_tree: bool = True,
        flatten: bool = False,
        collision: CollisionPolicy | None = None,
        allow_external: bool | None = None,
        debug_trace: bool | None = None,
        include_stack: bool | None = None,
    ) -> UnpackResult:
        _collision = collision or _collision_from_resolver(
            self._resolver, "file_io.archives.flatten.collision", CollisionPolicy.ERROR
        )
        _allow_external = allow_external
        if _allow_external is None:
            _allow_external = _bool_from_resolver(
                self._resolver, "file_io.archives.allow_external", True
            )

        _debug_trace = debug_trace
        if _debug_trace is None:
            _debug_trace = _bool_from_resolver(
                self._resolver, "file_io.archives.debug.include_trace", False
            )

        _include_stack = include_stack
        if _include_stack is None:
            _include_stack = _bool_from_resolver(
                self._resolver, "file_io.archives.debug.include_stack", False
            )

        trace: list[OpEvent] = []
        _fmt = self._resolve_format(src_root, src_archive_path, fmt=fmt, autodetect=autodetect)
        backend = self._select_backend_for_unpack(_fmt, allow_external=_allow_external)

        trace.append(
            OpEvent(
                op="unpack",
                phase=OpPhase.PLANNED,
                details={"format": _fmt.value, "backend": backend},
            )
        )
        try:
            self._fs.mkdir(dst_root, dst_dir, parents=True, exist_ok=True)
            if _fmt == ArchiveFormat.ZIP:
                files, total = self._unpack_zip(
                    src_root,
                    src_archive_path,
                    dst_root,
                    dst_dir,
                    preserve_tree,
                    flatten,
                    _collision,
                )
            elif _fmt in (ArchiveFormat.TAR, ArchiveFormat.TAR_GZ, ArchiveFormat.TAR_XZ):
                files, total = self._unpack_tar(
                    src_root,
                    src_archive_path,
                    dst_root,
                    dst_dir,
                    _fmt,
                    preserve_tree,
                    flatten,
                    _collision,
                )
            else:
                files, total = self._unpack_external(
                    src_root,
                    src_archive_path,
                    dst_root,
                    dst_dir,
                    _fmt,
                    preserve_tree,
                    flatten,
                    _collision,
                )
            trace.append(
                OpEvent(op="unpack", phase=OpPhase.OK, details={"files": files, "bytes": total})
            )
            return UnpackResult(
                format=_fmt,
                backend=backend,
                dst_root=dst_root.value,
                dst_dir=dst_dir,
                files_unpacked=files,
                total_bytes=total,
                warnings=[],
                trace=trace if _debug_trace else [],
            )
        except Exception as e:
            details: dict[str, object] = {"error": str(e)}
            if _include_stack:
                import traceback

                details["stack"] = traceback.format_exc()
            trace.append(OpEvent(op="unpack", phase=OpPhase.ERROR, details=details))
            if isinstance(e, FileError):
                raise
            raise FileError(str(e)) from e

    def plan_pack(
        self,
        src_root: RootName,
        src_dir: str,
        dst_root: RootName,
        dst_archive_path: str,
        *,
        fmt: ArchiveFormat,
        preserve_tree: bool = True,
        flatten: bool = False,
        collision: CollisionPolicy | None = None,
        allow_external: bool | None = None,
        debug: bool = False,
    ) -> PackPlan:
        _collision = collision or _collision_from_resolver(
            self._resolver, "file_io.archives.flatten.collision", CollisionPolicy.ERROR
        )
        _allow_external = allow_external
        if _allow_external is None:
            _allow_external = _bool_from_resolver(
                self._resolver, "file_io.archives.allow_external", True
            )

        backend = self._select_backend_for_pack(fmt, allow_external=_allow_external)

        entries = self._list_files_under(src_root, src_dir)
        mapped, collisions = self._map_entry_names(
            entries, preserve_tree=preserve_tree, flatten=flatten, collision=_collision
        )

        warnings: list[str] = []
        if fmt == ArchiveFormat.RAR and backend != "external":
            warnings.append("RAR pack requested but external backend is not available")

        if debug:
            log.debug(
                f"plan_pack format={fmt} backend={backend} entries={len(entries)} "
                f"collisions={len(collisions)}"
            )

        return PackPlan(
            format=fmt,
            backend=backend,
            src_root=src_root.value,
            src_dir=src_dir,
            dst_root=dst_root.value,
            dst_archive_path=dst_archive_path,
            preserve_tree=preserve_tree,
            flatten=flatten,
            collision=_collision,
            entries=mapped,
            collisions=collisions,
            warnings=warnings,
        )

    def pack(
        self,
        src_root: RootName,
        src_dir: str,
        dst_root: RootName,
        dst_archive_path: str,
        *,
        fmt: ArchiveFormat | None = None,
        autodetect: bool = False,
        preserve_tree: bool = True,
        flatten: bool = False,
        collision: CollisionPolicy | None = None,
        allow_external: bool | None = None,
        debug_trace: bool | None = None,
        include_stack: bool | None = None,
    ) -> PackResult:
        _collision = collision or _collision_from_resolver(
            self._resolver, "file_io.archives.flatten.collision", CollisionPolicy.ERROR
        )
        _allow_external = allow_external
        if _allow_external is None:
            _allow_external = _bool_from_resolver(
                self._resolver, "file_io.archives.allow_external", True
            )

        _debug_trace = debug_trace
        if _debug_trace is None:
            _debug_trace = _bool_from_resolver(
                self._resolver, "file_io.archives.debug.include_trace", False
            )

        _include_stack = include_stack
        if _include_stack is None:
            _include_stack = _bool_from_resolver(
                self._resolver, "file_io.archives.debug.include_stack", False
            )

        warnings: list[str] = []

        if autodetect:
            detected = self.detect_format(dst_root, dst_archive_path)
            fmt = detected.format

        if fmt is None:
            raise ValueError("fmt is required unless autodetect=True")

        trace: list[OpEvent] = []
        backend = self._select_backend_for_pack(fmt, allow_external=_allow_external)

        trace.append(
            OpEvent(
                op="pack", phase=OpPhase.PLANNED, details={"format": fmt.value, "backend": backend}
            )
        )
        try:
            self._fs.mkdir(
                dst_root, str(Path(dst_archive_path).parent), parents=True, exist_ok=True
            )
            if fmt == ArchiveFormat.ZIP:
                files, total = self._pack_zip(
                    src_root,
                    src_dir,
                    dst_root,
                    dst_archive_path,
                    preserve_tree,
                    flatten,
                    _collision,
                )
                is_det = True
            elif fmt in (ArchiveFormat.TAR, ArchiveFormat.TAR_GZ, ArchiveFormat.TAR_XZ):
                files, total = self._pack_tar(
                    src_root,
                    src_dir,
                    dst_root,
                    dst_archive_path,
                    fmt,
                    preserve_tree,
                    flatten,
                    _collision,
                )
                is_det = True
            else:
                files, total = self._pack_external(
                    src_root,
                    src_dir,
                    dst_root,
                    dst_archive_path,
                    fmt,
                    preserve_tree,
                    flatten,
                    _collision,
                )
                is_det = False
            trace.append(
                OpEvent(op="pack", phase=OpPhase.OK, details={"files": files, "bytes": total})
            )
            return PackResult(
                format=fmt,
                backend=backend,
                dst_root=dst_root.value,
                dst_archive_path=dst_archive_path,
                files_packed=files,
                total_bytes=total,
                is_deterministic=is_det,
                warnings=warnings,
                trace=trace if _debug_trace else [],
            )
        except Exception as e:
            details: dict[str, object] = {"error": str(e)}
            if _include_stack:
                import traceback

                details["stack"] = traceback.format_exc()
            trace.append(OpEvent(op="pack", phase=OpPhase.ERROR, details=details))
            if isinstance(e, FileError):
                raise
            raise FileError(str(e)) from e

    def _resolve_format(
        self,
        src_root: RootName,
        src_archive_path: str,
        *,
        fmt: ArchiveFormat | None,
        autodetect: bool,
    ) -> ArchiveFormat:
        if fmt is not None:
            return fmt
        if autodetect:
            return self.detect_format(src_root, src_archive_path).format
        raise FileError("Archive format not specified; set fmt or enable autodetect")

    def _select_backend_for_unpack(self, fmt: ArchiveFormat, *, allow_external: bool) -> str:
        if fmt in (
            ArchiveFormat.ZIP,
            ArchiveFormat.TAR,
            ArchiveFormat.TAR_GZ,
            ArchiveFormat.TAR_XZ,
        ):
            return "stdlib"
        if not allow_external:
            raise FileError(
                f"External backend required for format {fmt.value} but allow_external is false"
            )
        return "external"

    def _select_backend_for_pack(self, fmt: ArchiveFormat, *, allow_external: bool) -> str:
        if fmt in (
            ArchiveFormat.ZIP,
            ArchiveFormat.TAR,
            ArchiveFormat.TAR_GZ,
            ArchiveFormat.TAR_XZ,
        ):
            return "stdlib"
        if not allow_external:
            raise FileError(
                f"External backend required for format {fmt.value} but allow_external is false"
            )
        return "external"

    def _list_entries_for_plan(
        self, src_root: RootName, src_archive_path: str, fmt: ArchiveFormat, backend: str
    ) -> tuple[list[str], list[str]]:
        warnings: list[str] = []
        abs_path = self._fs.resolve_abs_path(src_root, src_archive_path)
        if backend == "stdlib":
            if fmt == ArchiveFormat.ZIP:
                with zipfile.ZipFile(abs_path, "r") as zf:
                    return _stable_sorted(
                        [n for n in zf.namelist() if not n.endswith("/")]
                    ), warnings
            if fmt in (ArchiveFormat.TAR, ArchiveFormat.TAR_GZ, ArchiveFormat.TAR_XZ):
                mode = cast(
                    TarReadMode,
                    {"tar": "r:", "tar.gz": "r:gz", "tar.xz": "r:xz"}[fmt.value],
                )
                with tarfile.open(name=str(abs_path), mode=mode) as tf:
                    names = [m.name for m in tf.getmembers() if m.isfile()]
                    return _stable_sorted(names), warnings
        if backend == "external":
            entries = self._list_entries_external(fmt, abs_path)
            return _stable_sorted(entries), warnings
        warnings.append("Entry listing not available for selected backend; plan will be partial")
        return [], warnings

    def _list_entries_external(self, fmt: ArchiveFormat, abs_path: Path) -> list[str]:
        """List archive entries without extracting.

        Preference order:
        - 7z (works for many formats, including rar)
        - unrar (rar-only)

        Raises FileError if no suitable external lister is available.
        """
        if shutil.which("7z"):
            # 7z -slt produces stable key/value blocks separated by blank lines.
            cmd = ["7z", "l", "-slt", str(abs_path)]
            res = subprocess.run(cmd, check=True, capture_output=True, text=True)
            entries: list[str] = []
            cur_path: str | None = None
            cur_attr: str | None = None

            def _flush() -> None:
                nonlocal cur_path, cur_attr
                if not cur_path:
                    cur_path, cur_attr = None, None
                    return
                is_dir = False
                if cur_attr is not None:
                    is_dir = cur_attr.strip().startswith("D")
                if not is_dir:
                    p = cur_path.replace("\\\\", "/").lstrip("/")
                    if p and not p.endswith("/"):
                        entries.append(p)
                cur_path, cur_attr = None, None

            for line in res.stdout.splitlines():
                s = line.strip()
                if not s:
                    _flush()
                    continue
                if s.startswith("Path = "):
                    cur_path = s.split("=", 1)[1].strip()
                    continue
                if s.startswith("Attributes = "):
                    cur_attr = s.split("=", 1)[1].strip()
                    continue
            _flush()
            return _stable_sorted(entries)

        if fmt == ArchiveFormat.RAR and shutil.which("unrar"):
            # 'unrar vb' prints bare file names, one per line.
            cmd = ["unrar", "vb", str(abs_path)]
            res = subprocess.run(cmd, check=True, capture_output=True, text=True)
            entries = []
            for line in res.stdout.splitlines():
                s = line.strip()
                if not s:
                    continue
                p = s.replace("\\\\", "/").lstrip("/")
                if p and not p.endswith("/"):
                    entries.append(p)
            return _stable_sorted(entries)

        raise FileError(
            f"No external listing tool available for {fmt.value}; install 7z (preferred) or unrar"
        )

    def _map_entry_names(
        self,
        entries: list[str],
        *,
        preserve_tree: bool,
        flatten: bool,
        collision: CollisionPolicy,
    ) -> tuple[list[str], list[str]]:
        mapped: list[str] = []
        collisions: list[str] = []
        used: set[str] = set()
        for name in _stable_sorted(entries):
            out = name
            if not preserve_tree or flatten:
                out = _apply_flatten(name)
            if out in used:
                if collision == CollisionPolicy.ERROR:
                    collisions.append(out)
                    continue
                if collision == CollisionPolicy.OVERWRITE:
                    mapped.append(out)
                    used.add(out)
                    continue
                if collision == CollisionPolicy.RENAME:
                    out2 = _rename_for_collision(used, out)
                    mapped.append(out2)
                    used.add(out2)
                    continue
            mapped.append(out)
            used.add(out)
        return mapped, _stable_sorted(collisions)

    def _list_files_under(self, src_root: RootName, src_dir: str) -> list[str]:
        base = self._fs.resolve_abs_path(src_root, src_dir)
        if not base.exists():
            raise FileError(f"Source dir not found: {src_dir}")
        if not base.is_dir():
            raise FileError(f"Source path is not a directory: {src_dir}")
        rels: list[str] = []
        for p in base.rglob("*"):
            if p.is_file():
                rels.append(str(p.relative_to(base)).replace(os.sep, "/"))
        return _stable_sorted(rels)

    def _unpack_zip(
        self,
        src_root: RootName,
        src_archive_path: str,
        dst_root: RootName,
        dst_dir: str,
        preserve_tree: bool,
        flatten: bool,
        collision: CollisionPolicy,
    ) -> tuple[int, int]:
        abs_src = self._fs.resolve_abs_path(src_root, src_archive_path)
        abs_dst = self._fs.resolve_abs_path(dst_root, dst_dir)
        files = 0
        total = 0
        used: set[str] = set()
        with zipfile.ZipFile(abs_src, "r") as zf:
            for info in sorted(
                [i for i in zf.infolist() if not i.is_dir()], key=lambda x: x.filename
            ):
                name = info.filename
                out = name if preserve_tree and not flatten else _apply_flatten(name)
                out = out.lstrip("/")
                if out in used:
                    if collision == CollisionPolicy.ERROR:
                        raise FileError(f"Collision while unpacking (flatten={flatten}): {out}")
                    if collision == CollisionPolicy.RENAME:
                        out = _rename_for_collision(used, out)
                    # OVERWRITE keeps out as-is
                used.add(out)
                dst_path = (abs_dst / out).resolve()
                try:
                    dst_path.relative_to(abs_dst.resolve())
                except ValueError:
                    raise FileError(f"Archive entry escapes destination: {name}") from None
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as src_f, open(dst_path, "wb") as dst_f:
                    shutil.copyfileobj(src_f, dst_f)
                    total += int(info.file_size)
                files += 1
        return files, total

    def _unpack_tar(
        self,
        src_root: RootName,
        src_archive_path: str,
        dst_root: RootName,
        dst_dir: str,
        fmt: ArchiveFormat,
        preserve_tree: bool,
        flatten: bool,
        collision: CollisionPolicy,
    ) -> tuple[int, int]:
        abs_src = self._fs.resolve_abs_path(src_root, src_archive_path)
        abs_dst = self._fs.resolve_abs_path(dst_root, dst_dir)
        mode = cast(
            TarReadMode,
            {"tar": "r:", "tar.gz": "r:gz", "tar.xz": "r:xz"}[fmt.value],
        )
        files = 0
        total = 0
        used: set[str] = set()
        with tarfile.open(name=str(abs_src), mode=mode) as tf:
            members = [m for m in tf.getmembers() if m.isfile()]
            for m in sorted(members, key=lambda x: x.name):
                name = m.name
                out = name if preserve_tree and not flatten else _apply_flatten(name)
                out = out.lstrip("/")
                if out in used:
                    if collision == CollisionPolicy.ERROR:
                        raise FileError(f"Collision while unpacking (flatten={flatten}): {out}")
                    if collision == CollisionPolicy.RENAME:
                        out = _rename_for_collision(used, out)
                used.add(out)
                dst_path = (abs_dst / out).resolve()
                try:
                    dst_path.relative_to(abs_dst.resolve())
                except ValueError:
                    raise FileError(f"Archive entry escapes destination: {name}") from None
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                f = tf.extractfile(m)
                if f is None:
                    continue
                with contextlib.closing(f), open(dst_path, "wb") as out_f:
                    shutil.copyfileobj(f, out_f)
                total += int(m.size)
                files += 1
        return files, total

    def _unpack_external(
        self,
        src_root: RootName,
        src_archive_path: str,
        dst_root: RootName,
        dst_dir: str,
        fmt: ArchiveFormat,
        preserve_tree: bool,
        flatten: bool,
        collision: CollisionPolicy,
    ) -> tuple[int, int]:
        abs_src = self._fs.resolve_abs_path(src_root, src_archive_path)
        abs_dst = self._fs.resolve_abs_path(dst_root, dst_dir)

        # For external tools, prefer preserve tree; flatten is supported by post-processing.
        tool = self._pick_external_unpack_tool(fmt)
        if tool == "7z":
            cmd = ["7z", "x", "-y", str(abs_src), f"-o{abs_dst}"]
        elif tool == "unrar":
            cmd = ["unrar", "x", "-o+", str(abs_src), str(abs_dst)]
        else:
            raise FileError(f"No external unpack tool available for {fmt.value}")

        subprocess.run(cmd, check=True, capture_output=True, text=True)

        # Optionally flatten.
        if flatten or not preserve_tree:
            files = self._flatten_dir(abs_dst, collision=collision)
        else:
            files = [p for p in abs_dst.rglob("*") if p.is_file()]
        total = sum(p.stat().st_size for p in files)
        return len(files), total

    def _pick_external_unpack_tool(self, fmt: ArchiveFormat) -> str:
        # Currently only for RAR/7Z.
        if shutil.which("7z"):
            return "7z"
        if fmt == ArchiveFormat.RAR and shutil.which("unrar"):
            return "unrar"
        raise FileError(f"No external backend found for {fmt.value}; install 7z or unrar")

    def _flatten_dir(self, base: Path, *, collision: CollisionPolicy) -> list[Path]:
        files = [p for p in base.rglob("*") if p.is_file()]
        files_sorted = sorted(files, key=lambda p: str(p.relative_to(base)).replace(os.sep, "/"))
        used: set[str] = set()
        out_files: list[Path] = []
        for p in files_sorted:
            name = p.name
            if name in used:
                if collision == CollisionPolicy.ERROR:
                    raise FileError(f"Collision while flattening extracted files: {name}")
                if collision == CollisionPolicy.RENAME:
                    name = _rename_for_collision(used, name)
            used.add(name)
            dst = base / name
            if p.resolve() != dst.resolve():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(p), str(dst))
            out_files.append(dst)
        # Remove now-empty dirs
        for d in sorted([p for p in base.rglob("*") if p.is_dir()], reverse=True):
            with contextlib.suppress(OSError):
                d.rmdir()
        return out_files

    def _pack_zip(
        self,
        src_root: RootName,
        src_dir: str,
        dst_root: RootName,
        dst_archive_path: str,
        preserve_tree: bool,
        flatten: bool,
        collision: CollisionPolicy,
    ) -> tuple[int, int]:
        abs_src_dir = self._fs.resolve_abs_path(src_root, src_dir)
        abs_dst = self._fs.resolve_abs_path(dst_root, dst_archive_path)
        entries = self._list_files_under(src_root, src_dir)
        mapped, collisions = self._map_entry_names(
            entries, preserve_tree=preserve_tree, flatten=flatten, collision=collision
        )
        if collisions:
            raise FileError(f"Collisions while packing: {', '.join(collisions)}")
        files = 0
        total = 0
        abs_dst.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(abs_dst, "w") as zf:
            for rel, arcname in zip(entries, mapped, strict=True):
                p = abs_src_dir / Path(rel)
                data = p.read_bytes()
                zi = _zipinfo_deterministic(arcname)
                zf.writestr(zi, data, compress_type=zipfile.ZIP_DEFLATED)
                files += 1
                total += len(data)
        return files, total

    def _pack_tar(
        self,
        src_root: RootName,
        src_dir: str,
        dst_root: RootName,
        dst_archive_path: str,
        fmt: ArchiveFormat,
        preserve_tree: bool,
        flatten: bool,
        collision: CollisionPolicy,
    ) -> tuple[int, int]:
        abs_src_dir = self._fs.resolve_abs_path(src_root, src_dir)
        abs_dst = self._fs.resolve_abs_path(dst_root, dst_archive_path)
        entries = self._list_files_under(src_root, src_dir)
        mapped, collisions = self._map_entry_names(
            entries, preserve_tree=preserve_tree, flatten=flatten, collision=collision
        )
        if collisions:
            raise FileError(f"Collisions while packing: {', '.join(collisions)}")
        mode = cast(
            TarWriteMode,
            {"tar": "w:", "tar.gz": "w:gz", "tar.xz": "w:xz"}[fmt.value],
        )
        files = 0
        total = 0
        abs_dst.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(name=str(abs_dst), mode=mode) as tf:
            for rel, arcname in zip(entries, mapped, strict=True):
                p = abs_src_dir / Path(rel)
                data = p.read_bytes()
                ti = _tarinfo_deterministic(arcname, size=len(data))
                tf.addfile(ti, io.BytesIO(data))
                files += 1
                total += len(data)
        return files, total

    def _pack_external(
        self,
        src_root: RootName,
        src_dir: str,
        dst_root: RootName,
        dst_archive_path: str,
        fmt: ArchiveFormat,
        preserve_tree: bool,
        flatten: bool,
        collision: CollisionPolicy,
    ) -> tuple[int, int]:
        if fmt != ArchiveFormat.RAR:
            raise FileError(f"External packing not supported for format {fmt.value}")
        abs_src_dir = self._fs.resolve_abs_path(src_root, src_dir)
        abs_dst = self._fs.resolve_abs_path(dst_root, dst_archive_path)
        if not shutil.which("rar"):
            raise FileError("RAR pack requested but 'rar' binary is not available on this system")
        # Note: rar does not guarantee deterministic output across versions.
        cmd = ["rar", "a", "-r", str(abs_dst), "."]
        subprocess.run(
            cmd,
            check=True,
            cwd=str(abs_src_dir),
            capture_output=True,
            text=True,
        )
        files = len([p for p in abs_src_dir.rglob("*") if p.is_file()])
        total = abs_dst.stat().st_size if abs_dst.exists() else 0
        return files, total
