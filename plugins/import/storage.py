"""Atomic persistence helpers for import wizard engine.

All writes are atomic (temp + rename) under file_io roots.
ASCII-only.
"""

from __future__ import annotations

import json
from typing import Any

from plugins.file_io.service import FileService, RootName


def _atomic_write_bytes(
    fs: FileService,
    root: RootName,
    rel_path: str,
    data: bytes,
) -> None:
    tmp_path = f"{rel_path}.tmp"
    with fs.open_write(root, tmp_path, overwrite=True, mkdir_parents=True) as f:
        f.write(data)
    fs.rename(root, tmp_path, rel_path, overwrite=True)


def atomic_write_json(
    fs: FileService,
    root: RootName,
    rel_path: str,
    obj: Any,
) -> None:
    data = json.dumps(
        obj,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    _atomic_write_bytes(fs, root, rel_path, data)


def atomic_write_text(
    fs: FileService,
    root: RootName,
    rel_path: str,
    text: str,
) -> None:
    _atomic_write_bytes(fs, root, rel_path, text.encode("utf-8"))


def read_json(fs: FileService, root: RootName, rel_path: str) -> Any:
    with fs.open_read(root, rel_path) as f:
        data = f.read()
    return json.loads(data.decode("utf-8"))


def append_jsonl(fs: FileService, root: RootName, rel_path: str, obj: Any) -> None:
    line = json.dumps(
        obj,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    with fs.open_append(root, rel_path, mkdir_parents=True) as f:
        f.write(line.encode("utf-8"))
        f.write(b"\n")
