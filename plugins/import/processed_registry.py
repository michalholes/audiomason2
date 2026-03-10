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

from typing import Any

from plugins.file_io.service import FileService, RootName

from .storage import atomic_write_json, read_json

_REGISTRY_PATH = "import/processed/processed_registry.json"
_SCHEMA_VERSION = 1


def load_registry(fs: FileService) -> dict[str, Any]:
    if fs.exists(RootName.WIZARDS, _REGISTRY_PATH):
        data = read_json(fs, RootName.WIZARDS, _REGISTRY_PATH)
        if isinstance(data, dict):
            return data
    return {"schema_version": _SCHEMA_VERSION, "books": {}}


def _ensure_registry_shape(reg: Any) -> dict[str, Any]:
    if not isinstance(reg, dict):
        return {"schema_version": _SCHEMA_VERSION, "books": {}}
    books = reg.get("books")
    if not isinstance(books, dict):
        books = {}
    sv = reg.get("schema_version")
    if sv != _SCHEMA_VERSION:
        sv = _SCHEMA_VERSION
    return {"schema_version": sv, "books": dict(books)}


def _normalize_authority(action_any: dict[str, Any]) -> dict[str, Any]:
    authority_any = action_any.get("authority")
    authority = dict(authority_any) if isinstance(authority_any, dict) else {}

    book_any = authority.get("book")
    book = dict(book_any) if isinstance(book_any, dict) else {}
    normalized_book = {
        key: str(value)
        for key, value in book.items()
        if isinstance(key, str) and isinstance(value, str) and value
    }

    meta_any = authority.get("metadata_tags")
    meta = dict(meta_any) if isinstance(meta_any, dict) else {}
    field_map_any = meta.get("field_map")
    field_map = dict(field_map_any) if isinstance(field_map_any, dict) else {}
    values_any = meta.get("values")
    values = dict(values_any) if isinstance(values_any, dict) else {}
    normalized_meta = {
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

    publish_any = authority.get("publish")
    publish = dict(publish_any) if isinstance(publish_any, dict) else {}
    normalized_publish = {
        key: str(value)
        for key, value in publish.items()
        if isinstance(key, str) and isinstance(value, str) and value
    }

    out: dict[str, Any] = {}
    if normalized_book:
        out["book"] = normalized_book
    if normalized_meta["field_map"] or normalized_meta["values"]:
        out["metadata_tags"] = normalized_meta
    if normalized_publish:
        out["publish"] = normalized_publish
    return out


def iter_import_book_records(job_requests: dict[str, Any]) -> list[dict[str, Any]]:
    """Return deterministic per-book records derived from job_requests."""

    if not isinstance(job_requests, dict):
        return []

    actions_any = job_requests.get("actions")
    actions = actions_any if isinstance(actions_any, list) else []
    records: list[dict[str, Any]] = []
    for action_any in actions:
        if not isinstance(action_any, dict):
            continue
        if action_any.get("type") != "import.book":
            continue
        book_id = action_any.get("book_id")
        source_any = action_any.get("source")
        target_any = action_any.get("target")
        if not isinstance(book_id, str) or not book_id:
            continue
        if not isinstance(source_any, dict) or not isinstance(target_any, dict):
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
        caps = caps_any if isinstance(caps_any, list) else []
        cap_summary: list[dict[str, Any]] = []
        for cap_any in caps:
            if not isinstance(cap_any, dict):
                continue
            kind = cap_any.get("kind")
            if not isinstance(kind, str) or not kind:
                continue
            cap_summary.append(
                {
                    "kind": kind,
                    "order": int(cap_any.get("order") or 0),
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


def apply_successful_job_requests(fs: FileService, job_requests: dict[str, Any]) -> bool:
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
    books: dict[str, Any] = reg["books"]

    changed = False
    for record in records:
        book_id = str(record["book_id"])
        entry: dict[str, Any] = {
            "source_relative_path": str(record["source_relative_path"]),
            "target_root": str(record["target_root"]),
            "target_relative_path": str(record["target_relative_path"]),
            "idempotency_key": idem_key,
            "config_fingerprint": config_fp,
        }
        if plan_fp is not None:
            entry["plan_fingerprint"] = plan_fp
        authority_any = record.get("authority")
        authority = dict(authority_any) if isinstance(authority_any, dict) else {}
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
