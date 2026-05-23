"""Processed books registry for import plugin.

This module is file_io-only and contains no core imports.

Registry location (RootName.WIZARDS):
  import/processed/processed_registry.json

Schema v1:
  {
    "schema_version": 1,
    "books": {
      "<book_id>": {
        "source_relative_path": "...",
        "target_root": "stage"|"outbox",
        "target_relative_path": "...",
        "idempotency_key": "...",
        "config_fingerprint": "...",
        "plan_fingerprint": "...",  # optional
        "authority": { ... }          # optional
      }
    }
  }

ASCII-only.
"""

from __future__ import annotations

from contextlib import suppress
from typing import TypeGuard

from plugins.file_io.service import FileService, RootName

from .storage import atomic_write_json, read_json

_REGISTRY_PATH = "import/processed/processed_registry.json"
_SCHEMA_VERSION = 1


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _to_int_or_default(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def load_registry(fs: FileService) -> dict[str, object]:
    if fs.exists(RootName.WIZARDS, _REGISTRY_PATH):
        data = read_json(fs, RootName.WIZARDS, _REGISTRY_PATH)
        if isinstance(data, dict):
            return data
    return {"schema_version": _SCHEMA_VERSION, "books": {}}


def _ensure_registry_shape(reg: object) -> dict[str, object]:
    if not _is_str_object_dict(reg):
        return {"schema_version": _SCHEMA_VERSION, "books": {}}
    books = reg.get("books")
    if not _is_str_object_dict(books):
        books = {}
    sv = reg.get("schema_version")
    if sv != _SCHEMA_VERSION:
        sv = _SCHEMA_VERSION
    return {"schema_version": sv, "books": dict(books)}


def _normalize_authority(action_any: dict[str, object]) -> dict[str, object]:
    authority_any = action_any.get("authority")
    authority = _as_str_object_dict(authority_any)

    book_any = authority.get("book")
    book = _as_str_object_dict(book_any)
    normalized_book = {
        key: str(value)
        for key, value in book.items()
        if isinstance(key, str) and isinstance(value, str) and value
    }

    meta_any = authority.get("metadata_tags")
    meta = _as_str_object_dict(meta_any)
    field_map_any = meta.get("field_map")
    field_map = _as_str_object_dict(field_map_any)
    values_any = meta.get("values")
    values = _as_str_object_dict(values_any)
    normalized_meta: dict[str, object] = {
        "field_map": {
            str(key): str(value)
            for key, value in field_map.items()
            if isinstance(key, str) and isinstance(value, str) and value
        },
        "values": {
            str(key): str(value)
            for key, value in values.items()
            if isinstance(key, str) and isinstance(value, str) and value
        },
    }
    track_start = meta.get("track_start")
    if track_start is not None:
        with suppress(TypeError, ValueError):
            normalized_meta["track_start"] = int(str(track_start).strip())

    publish_any = authority.get("publish")
    publish = _as_str_object_dict(publish_any)
    normalized_publish = {
        key: str(value)
        for key, value in publish.items()
        if isinstance(key, str) and isinstance(value, str) and value
    }

    out: dict[str, object] = {}
    if normalized_book:
        out["book"] = normalized_book
    if normalized_meta["field_map"] or normalized_meta["values"]:
        out["metadata_tags"] = normalized_meta
    if normalized_publish:
        out["publish"] = normalized_publish
    return out


def iter_import_book_records(job_requests: dict[str, object]) -> list[dict[str, object]]:
    """Return deterministic per-book records derived from job_requests."""

    if not _is_str_object_dict(job_requests):
        return []

    actions_any = job_requests.get("actions")
    actions = actions_any if _is_object_list(actions_any) else []
    records: list[dict[str, object]] = []
    for action_any in actions:
        if not _is_str_object_dict(action_any):
            continue
        if action_any.get("type") != "import.book":
            continue
        book_id = action_any.get("book_id")
        source_any = action_any.get("source")
        target_any = action_any.get("target")
        if not isinstance(book_id, str) or not book_id:
            continue
        if not _is_str_object_dict(source_any) or not _is_str_object_dict(target_any):
            continue

        source_root = source_any.get("root")
        source_rel = source_any.get("relative_path")
        target_root = target_any.get("root")
        target_rel = target_any.get("relative_path")
        if not isinstance(source_root, str) or not source_root:
            continue
        if not isinstance(source_rel, str) or not source_rel:
            continue
        if not isinstance(target_root, str) or target_root not in {"stage", "outbox"}:
            continue
        if not isinstance(target_rel, str) or not target_rel:
            continue

        caps_any = action_any.get("capabilities")
        caps = caps_any if _is_object_list(caps_any) else []
        cap_summary: list[dict[str, object]] = []
        for cap_any in caps:
            if not _is_str_object_dict(cap_any):
                continue
            kind = cap_any.get("kind")
            if not isinstance(kind, str) or not kind:
                continue
            cap_summary.append(
                {
                    "kind": kind,
                    "order": _to_int_or_default(cap_any.get("order"), 0),
                }
            )

        records.append(
            {
                "book_id": book_id,
                "source_root": source_root,
                "source_relative_path": source_rel,
                "target_root": target_root,
                "target_relative_path": target_rel,
                "authority": _normalize_authority(action_any),
                "capabilities": cap_summary,
            }
        )
    return records


def apply_successful_job_requests(fs: FileService, job_requests: dict[str, object]) -> bool:
    """Update the processed registry from job_requests.

    Returns True if registry was updated and persisted, else False.

    The caller is responsible for ensuring the corresponding job completed successfully.
    """

    if not isinstance(job_requests, dict):
        return False

    idem_key = job_requests.get("idempotency_key")
    config_fp = job_requests.get("config_fingerprint")
    if not isinstance(idem_key, str) or not idem_key:
        return False
    if not isinstance(config_fp, str) or not config_fp:
        return False

    records = iter_import_book_records(job_requests)
    if not records:
        return False

    plan_fp_any = job_requests.get("plan_fingerprint")
    plan_fp = plan_fp_any if isinstance(plan_fp_any, str) and plan_fp_any else None

    reg = _ensure_registry_shape(load_registry(fs))
    books = _as_str_object_dict(reg.get("books"))
    reg["books"] = books

    changed = False
    for record in records:
        book_id = str(record["book_id"])
        entry: dict[str, object] = {
            "source_relative_path": str(record["source_relative_path"]),
            "target_root": str(record["target_root"]),
            "target_relative_path": str(record["target_relative_path"]),
            "idempotency_key": idem_key,
            "config_fingerprint": config_fp,
        }
        if plan_fp is not None:
            entry["plan_fingerprint"] = plan_fp
        authority_any = record.get("authority")
        authority = _as_str_object_dict(authority_any)
        if authority:
            entry["authority"] = authority

        prev = books.get(book_id)
        if prev != entry:
            books[book_id] = entry
            changed = True

    if not changed:
        return False

    atomic_write_json(fs, RootName.WIZARDS, _REGISTRY_PATH, reg)
    return True
