"""Processed registry service.

Storage is performed via file_io capability (FileService) under the JOBS root.

The registry stores stable book identity keys. For Import Wizard integration,
the identity key is the book fingerprint key (algo:value).

ASCII-only.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

from .types import ProcessedRegistryStats

_BASE_DIR = "import/processed_registry"
_REGISTRY_PATH = f"{_BASE_DIR}/registry.json"


def fingerprint_key(*, algo: str, value: str) -> str:
    """Return the canonical identity key for a fingerprint."""
    algo = str(algo or "").strip()
    value = str(value or "").strip()
    if not algo:
        algo = "unknown"
    return f"{algo}:{value}" if value else f"{algo}:"


_AUDIO_EXT = {".mp3", ".m4a", ".m4b", ".flac", ".wav", ".ogg", ".opus"}
_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def _ext(rel_path: str) -> str:
    name = rel_path.rstrip("/").split("/")[-1].lower()
    if "." not in name:
        return ""
    return "." + name.split(".")[-1]


def build_import_identity_key(
    fs: FileService,
    *,
    source_root: RootName,
    book_rel_path: str,
    unit_type: str,
) -> str:
    """Build the canonical import identity key (fingerprint).

    This builder is shared by PHASE 0 (preflight) and PHASE 2 (processing).

    It is stat-based (path + size + mtime) and MUST NOT perform full-file hashing.
    """
    unit = str(unit_type or "").strip().lower()
    if unit == "file":
        st = fs.stat(source_root, book_rel_path)
        h = hashlib.sha256()
        h.update(book_rel_path.encode("utf-8"))
        h.update(b"\n")
        h.update(str(int(st.size)).encode("utf-8"))
        h.update(b"\n")
        h.update(f"{float(st.mtime):.6f}".encode())
        h.update(b"\n")
        return fingerprint_key(algo="sha256", value=h.hexdigest())

    entries = fs.list_dir(source_root, book_rel_path, recursive=True)
    items: list[tuple[str, int, float]] = []
    for e in entries:
        if e.is_dir:
            continue
        ext = _ext(e.rel_path)
        if ext not in _AUDIO_EXT and ext not in _IMG_EXT:
            continue
        items.append((e.rel_path, int(e.size or 0), float(e.mtime or 0.0)))

    h = hashlib.sha256()
    for rel, size, mtime in sorted(items):
        h.update(rel.encode("utf-8"))
        h.update(b"\n")
        h.update(str(int(size)).encode("utf-8"))
        h.update(b"\n")
        h.update(f"{mtime:.6f}".encode())
        h.update(b"\n")
    return fingerprint_key(algo="sha256", value=h.hexdigest())


def _emit_diag(event: str, *, operation: str, data: dict[str, Any]) -> None:
    try:
        env = build_envelope(
            event=event,
            component="import.processed_registry",
            operation=operation,
            data=data,
        )
        get_event_bus().publish(event, env)
    except Exception:
        return


class ProcessedRegistry:
    """Processed registry keyed by stable book identity."""

    def __init__(self, fs: FileService) -> None:
        self._fs = fs
        if not self._fs.exists(RootName.JOBS, _BASE_DIR):
            self._fs.mkdir(RootName.JOBS, _BASE_DIR, parents=True, exist_ok=True)

    def is_processed(self, identity_key: str) -> bool:
        _emit_diag("boundary.start", operation="is_processed", data={"identity_key": identity_key})
        data = self._load()
        res = identity_key in data
        _emit_diag(
            "boundary.end",
            operation="is_processed",
            data={"identity_key": identity_key, "status": "succeeded"},
        )
        return res

    def mark_processed(self, identity_key: str) -> None:
        _emit_diag(
            "boundary.start", operation="mark_processed", data={"identity_key": identity_key}
        )
        data = self._load()
        data.add(identity_key)
        self._store(data)
        _emit_diag(
            "boundary.end",
            operation="mark_processed",
            data={"identity_key": identity_key, "status": "succeeded"},
        )

    def unmark_processed(self, identity_key: str) -> None:
        _emit_diag(
            "boundary.start", operation="unmark_processed", data={"identity_key": identity_key}
        )
        data = self._load()
        if identity_key in data:
            data.remove(identity_key)
            self._store(data)
        _emit_diag(
            "boundary.end",
            operation="unmark_processed",
            data={"identity_key": identity_key, "status": "succeeded"},
        )

    def list_processed(self) -> list[str]:
        """Return sorted list of processed identity keys."""
        data = self._load()
        return sorted(data)

    def stats(self) -> ProcessedRegistryStats:
        data = self._load()
        return ProcessedRegistryStats(count=len(data))

    def _load(self) -> set[str]:
        if not self._fs.exists(RootName.JOBS, _REGISTRY_PATH):
            return set()
        with self._fs.open_read(RootName.JOBS, _REGISTRY_PATH) as f:
            txt = f.read().decode("utf-8")
        obj = json.loads(txt)
        if not isinstance(obj, list):
            return set()
        out = set()
        for v in obj:
            if isinstance(v, str) and v:
                out.add(v)
        return out

    def _store(self, data: set[str]) -> None:
        obj = sorted(data)
        txt = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        with self._fs.open_write(
            RootName.JOBS, _REGISTRY_PATH, overwrite=True, mkdir_parents=True
        ) as f:
            f.write(txt.encode("utf-8"))
