"""Import wizard editor storage helpers (plugin: import).

Provides canonical JSON load/save for the import wizard catalog and flow
models under the WIZARDS root.

Save rules:
- canonical JSON (UTF-8, ensure_ascii, sort keys, newline)
- atomic write (temp + rename)
- best-effort fsync when supported by the file handle

ASCII-only.
"""

from __future__ import annotations

import json
import os
from typing import Any

from plugins.file_io.service import FileService, RootName

CATALOG_REL_PATH = "import/catalog/catalog.json"
FLOW_REL_PATH = "import/flow/current.json"


def load_catalog(fs: FileService) -> Any:
    return _load_json(fs, RootName.WIZARDS, CATALOG_REL_PATH)


def load_flow(fs: FileService) -> Any:
    return _load_json(fs, RootName.WIZARDS, FLOW_REL_PATH)


def save_catalog(fs: FileService, obj: Any) -> None:
    _atomic_write_json(fs, RootName.WIZARDS, CATALOG_REL_PATH, obj)


def save_flow(fs: FileService, obj: Any) -> None:
    _atomic_write_json(fs, RootName.WIZARDS, FLOW_REL_PATH, obj)


def _load_json(fs: FileService, root: RootName, rel_path: str) -> Any:
    with fs.open_read(root, rel_path) as f:
        data = f.read()
    return json.loads(data.decode("utf-8"))


def _atomic_write_json(fs: FileService, root: RootName, rel_path: str, obj: Any) -> None:
    data = (
        json.dumps(
            obj,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    _atomic_write_bytes(fs, root, rel_path, data)


def _atomic_write_bytes(fs: FileService, root: RootName, rel_path: str, data: bytes) -> None:
    tmp_path = f"{rel_path}.tmp"
    with fs.open_write(root, tmp_path, overwrite=True, mkdir_parents=True) as f:
        f.write(data)
        _best_effort_fsync(f)
    fs.rename(root, tmp_path, rel_path, overwrite=True)


def _best_effort_fsync(f: Any) -> None:
    try:
        flush = getattr(f, "flush", None)
        if callable(flush):
            flush()
        fileno = getattr(f, "fileno", None)
        if callable(fileno):
            os.fsync(fileno())
    except Exception:
        return
