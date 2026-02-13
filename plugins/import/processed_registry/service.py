"""Processed registry service.

Storage is performed via file_io capability (FileService) under the JOBS root.

The registry stores stable book identity keys. For Import Wizard integration,
the identity key is the book fingerprint key (algo:value).

ASCII-only.
"""

from __future__ import annotations

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
