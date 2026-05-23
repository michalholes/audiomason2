"""Success-only ignore registry for import finalize side effects.

ASCII-only.
"""

from __future__ import annotations

from typing import TypeGuard

from plugins.file_io.service import FileService, RootName

from .processed_registry import iter_import_book_records
from .storage import atomic_write_json, read_json

_REGISTRY_PATH = "import/processed/ignore_registry.json"
_SCHEMA_VERSION = 1


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def load_registry(fs: FileService) -> dict[str, object]:
    if fs.exists(RootName.WIZARDS, _REGISTRY_PATH):
        data = read_json(fs, RootName.WIZARDS, _REGISTRY_PATH)
        if _is_str_object_dict(data):
            return data
    return {"schema_version": _SCHEMA_VERSION, "sources": []}


def _normalize_sources(data: object) -> list[dict[str, str]]:
    if not isinstance(data, list):
        return []
    seen: dict[tuple[str, str], dict[str, str]] = {}
    for item in data:
        if not _is_str_object_dict(item):
            continue
        root = item.get("root")
        rel = item.get("relative_path")
        if not isinstance(root, str) or not root:
            continue
        if not isinstance(rel, str) or not rel:
            continue
        seen[(root, rel)] = {"root": root, "relative_path": rel}
    return [seen[key] for key in sorted(seen.keys())]


def _ensure_registry_shape(reg: object) -> dict[str, object]:
    if not _is_str_object_dict(reg):
        return {"schema_version": _SCHEMA_VERSION, "sources": []}
    schema_version = reg.get("schema_version")
    if schema_version != _SCHEMA_VERSION:
        schema_version = _SCHEMA_VERSION
    return {
        "schema_version": schema_version,
        "sources": _normalize_sources(reg.get("sources")),
    }


def _source_ref(record: dict[str, object]) -> dict[str, str]:
    return {
        "root": str(record["source_root"]),
        "relative_path": str(record["source_relative_path"]),
    }


def apply_successful_job_requests(fs: FileService, job_requests: dict[str, object]) -> bool:
    """Update the ignore registry from successful import job_requests."""

    records = iter_import_book_records(job_requests)
    if not records:
        return False

    reg = _ensure_registry_shape(load_registry(fs))
    merged = _normalize_sources(reg.get("sources"))
    merged.extend([_source_ref(record) for record in records])
    normalized = _normalize_sources(merged)
    if normalized == reg["sources"]:
        return False

    reg["sources"] = normalized
    atomic_write_json(fs, RootName.WIZARDS, _REGISTRY_PATH, reg)
    return True
