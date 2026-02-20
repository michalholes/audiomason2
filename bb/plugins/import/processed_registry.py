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
        "plan_fingerprint": "..."   # optional
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


def apply_successful_job_requests(fs: FileService, job_requests: dict[str, Any]) -> bool:
    """Update the processed registry from job_requests.

    Returns True if registry was updated and persisted, else False.

    The caller is responsible for ensuring the corresponding job completed successfully.
    """

    if not isinstance(job_requests, dict):
        return False

    actions_any = job_requests.get("actions")
    if not isinstance(actions_any, list) or not actions_any:
        return False

    idem_key = job_requests.get("idempotency_key")
    config_fp = job_requests.get("config_fingerprint")
    if not isinstance(idem_key, str) or not idem_key:
        return False
    if not isinstance(config_fp, str) or not config_fp:
        return False

    plan_fp_any = job_requests.get("plan_fingerprint")
    plan_fp = plan_fp_any if isinstance(plan_fp_any, str) and plan_fp_any else None

    reg = _ensure_registry_shape(load_registry(fs))
    books: dict[str, Any] = reg["books"]

    changed = False
    for act in actions_any:
        if not isinstance(act, dict):
            continue
        if act.get("type") != "import.book":
            continue
        book_id = act.get("book_id")
        src_any = act.get("source")
        tgt_any = act.get("target")
        if not isinstance(book_id, str) or not book_id:
            continue
        if not isinstance(src_any, dict) or not isinstance(tgt_any, dict):
            continue
        src_rel = src_any.get("relative_path")
        tgt_root = tgt_any.get("root")
        tgt_rel = tgt_any.get("relative_path")
        if not isinstance(src_rel, str) or not src_rel:
            continue
        if not isinstance(tgt_root, str) or tgt_root not in {"stage", "outbox"}:
            continue
        if not isinstance(tgt_rel, str) or not tgt_rel:
            continue

        entry: dict[str, Any] = {
            "source_relative_path": src_rel,
            "target_root": tgt_root,
            "target_relative_path": tgt_rel,
            "idempotency_key": idem_key,
            "config_fingerprint": config_fp,
        }
        if plan_fp is not None:
            entry["plan_fingerprint"] = plan_fp

        prev = books.get(book_id)
        if prev != entry:
            books[book_id] = entry
            changed = True

    if not changed:
        return False

    atomic_write_json(fs, RootName.WIZARDS, _REGISTRY_PATH, reg)
    return True
