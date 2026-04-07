"""Import-owned file/materialization boundary helpers.

Resolver-friendly refs remain the only authority. Absolute paths are
materialized here only for execution-time needs.

ASCII-only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from plugins.file_io.import_runtime import normalize_relative_path
from plugins.file_io.service import FileService, RootName


def _normalize_root_name(root: str | RootName) -> RootName:
    return root if isinstance(root, RootName) else RootName(str(root))


def _source_ref_from_state(state: dict[str, Any]) -> tuple[RootName | None, str]:
    source_any = state.get("source")
    source = dict(source_any) if isinstance(source_any, dict) else {}
    root_text = str(source.get("root") or "").strip()
    rel = normalize_relative_path(str(source.get("relative_path") or ""))
    if not root_text:
        return None, rel
    try:
        return RootName(root_text), rel
    except ValueError:
        return None, rel


def _join_source_relative_path(*, source_prefix: str, source_relative_path: str) -> str:
    base = normalize_relative_path(source_prefix)
    rel = normalize_relative_path(source_relative_path)
    if not base:
        return rel
    if not rel:
        return base
    return f"{base}/{rel}"


def _materialize_root_dir(fs: FileService, root: str | RootName) -> Path:
    root_name = _normalize_root_name(root)
    root_dir = getattr(fs, "root_dir", None)
    if callable(root_dir):
        return root_dir(root_name)
    root_cfg = getattr(fs, "_root", None)
    if callable(root_cfg):
        cfg = root_cfg(root_name)
        path = getattr(cfg, "dir_path", None)
        if isinstance(path, Path):
            return path
    raise RuntimeError("file_io root materialization unavailable")


def _materialize_local_path(
    fs: FileService,
    root: str | RootName,
    rel_path: str,
    *,
    silent_polling_read: bool = False,
) -> Path:
    root_name = _normalize_root_name(root)
    rel = normalize_relative_path(rel_path)
    resolver = getattr(fs, "_resolve_local_path", None)
    if callable(resolver):
        return resolver(root_name, rel, silent_polling_read=silent_polling_read)
    resolve_abs = getattr(fs, "resolve_abs_path", None)
    if callable(resolve_abs):
        return resolve_abs(root_name, rel)
    base = _materialize_root_dir(fs, root_name)
    if not rel:
        return base
    return base / Path(*[part for part in rel.split("/") if part])


def _read_json_ref(fs: FileService, root: str | RootName, rel_path: str) -> dict[str, Any]:
    with fs.open_read(_normalize_root_name(root), normalize_relative_path(rel_path)) as handle:
        data = handle.read()
    parsed = json.loads(data.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("JSON artifact must be an object")
    return parsed


normalize_root_name = _normalize_root_name
source_ref_from_state = _source_ref_from_state
join_source_relative_path = _join_source_relative_path
materialize_root_dir = _materialize_root_dir
materialize_local_path = _materialize_local_path
read_json_ref = _read_json_ref

__all__ = [
    "join_source_relative_path",
    "materialize_local_path",
    "materialize_root_dir",
    "normalize_root_name",
    "read_json_ref",
    "source_ref_from_state",
]
