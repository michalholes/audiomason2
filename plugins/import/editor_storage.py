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

from .fingerprints import fingerprint_json
from .flow_config_defaults import DEFAULT_FLOW_CONFIG
from .flow_config_validation import normalize_flow_config

CATALOG_REL_PATH = "import/catalog/catalog.json"
FLOW_REL_PATH = "import/flow/current.json"
FLOW_CONFIG_REL_PATH = "import/config/flow_config.json"
FLOW_CONFIG_DRAFT_REL_PATH = "import/config/flow_config.draft.json"

HISTORY_DIR = "import/editor_history"
HISTORY_LIMIT = 5


def load_catalog(fs: FileService) -> Any:
    return _load_json(fs, RootName.WIZARDS, CATALOG_REL_PATH)


def load_flow(fs: FileService) -> Any:
    return _load_json(fs, RootName.WIZARDS, FLOW_REL_PATH)


def save_catalog(fs: FileService, obj: Any) -> None:
    raise ValueError("catalog is immutable; editor may only modify flow_config")


def save_flow(fs: FileService, obj: Any) -> None:
    raise ValueError("flow is immutable; editor may only modify flow_config")


def load_flow_config(fs: FileService) -> Any:
    return _load_json(fs, RootName.WIZARDS, FLOW_CONFIG_REL_PATH)


def save_flow_config(fs: FileService, obj: Any) -> None:
    """Save ACTIVE flow_config with history.

    This legacy helper persists directly to the ACTIVE file. It is still
    used for rollback and bootstrap flows.
    """

    _save_with_history(fs, kind="flow_config", rel_path=FLOW_CONFIG_REL_PATH, obj=obj)


def reset_catalog(fs: FileService) -> None:
    raise ValueError("catalog is immutable; editor may only modify flow_config")


def reset_flow(fs: FileService) -> None:
    raise ValueError("flow is immutable; editor may only modify flow_config")


def reset_flow_config(fs: FileService) -> None:
    save_flow_config(fs, DEFAULT_FLOW_CONFIG)


def list_history(fs: FileService, *, kind: str) -> list[str]:
    index = _load_history_index(fs, kind=kind)
    return list(index)


def rollback(fs: FileService, *, kind: str, fingerprint: str) -> None:
    rel = f"{HISTORY_DIR}/{kind}/{fingerprint}.json"
    obj = _load_json(fs, RootName.WIZARDS, rel)
    if kind == "flow_config":
        save_flow_config(fs, obj)
    else:
        raise ValueError("unknown kind")


# ---------------------------------------------------------------------------
# Deterministic Draft/Active/History lifecycle (FlowConfig)
# ---------------------------------------------------------------------------


def _strip_legacy_ui(obj: Any) -> Any:
    if isinstance(obj, dict) and "ui" in obj:
        out = dict(obj)
        out.pop("ui", None)
        return out
    return obj


def ensure_flow_config_active_exists(fs: FileService) -> dict[str, Any]:
    if not fs.exists(RootName.WIZARDS, FLOW_CONFIG_REL_PATH):
        boot = _strip_legacy_ui(DEFAULT_FLOW_CONFIG)
        canon = normalize_flow_config(boot)
        _atomic_write_json(fs, RootName.WIZARDS, FLOW_CONFIG_REL_PATH, canon)
        return canon

    raw = _load_json(fs, RootName.WIZARDS, FLOW_CONFIG_REL_PATH)
    had_ui = isinstance(raw, dict) and "ui" in raw
    cfg = normalize_flow_config(_strip_legacy_ui(raw))

    if had_ui:
        _atomic_write_json(fs, RootName.WIZARDS, FLOW_CONFIG_REL_PATH, cfg)

    return cfg


def get_flow_config_draft(fs: FileService) -> dict[str, Any]:
    active = ensure_flow_config_active_exists(fs)
    if fs.exists(RootName.WIZARDS, FLOW_CONFIG_DRAFT_REL_PATH):
        draft_any = _load_json(fs, RootName.WIZARDS, FLOW_CONFIG_DRAFT_REL_PATH)
        draft_any = _strip_legacy_ui(draft_any)
        return normalize_flow_config(draft_any)
    return active


def put_flow_config_draft(fs: FileService, obj: Any) -> dict[str, Any]:
    canon = normalize_flow_config(obj)
    _atomic_write_json(fs, RootName.WIZARDS, FLOW_CONFIG_DRAFT_REL_PATH, canon)
    return canon


def reset_flow_config_draft(fs: FileService) -> dict[str, Any]:
    canon = normalize_flow_config(_strip_legacy_ui(DEFAULT_FLOW_CONFIG))
    _atomic_write_json(fs, RootName.WIZARDS, FLOW_CONFIG_DRAFT_REL_PATH, canon)
    return canon


def activate_flow_config_draft(fs: FileService) -> dict[str, Any]:
    active = ensure_flow_config_active_exists(fs)

    if not fs.exists(RootName.WIZARDS, FLOW_CONFIG_DRAFT_REL_PATH):
        raise ValueError("flow_config draft does not exist")

    draft_any = _load_json(fs, RootName.WIZARDS, FLOW_CONFIG_DRAFT_REL_PATH)
    draft_any = _strip_legacy_ui(draft_any)
    draft = normalize_flow_config(draft_any)

    cur_fp = fingerprint_json(active)
    new_fp = fingerprint_json(draft)
    if cur_fp != new_fp:
        _store_history_entry(fs, kind="flow_config", fingerprint=cur_fp, obj=active)
        _atomic_write_json(fs, RootName.WIZARDS, FLOW_CONFIG_REL_PATH, draft)
        active = draft

    fs.delete_file(RootName.WIZARDS, FLOW_CONFIG_DRAFT_REL_PATH)
    return active


def delete_flow_config_draft(fs: FileService) -> None:
    if fs.exists(RootName.WIZARDS, FLOW_CONFIG_DRAFT_REL_PATH):
        fs.delete_file(RootName.WIZARDS, FLOW_CONFIG_DRAFT_REL_PATH)


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


def _save_with_history(fs: FileService, *, kind: str, rel_path: str, obj: Any) -> None:
    # Snapshot current file into history (if it exists and differs).
    if fs.exists(RootName.WIZARDS, rel_path):
        current = _load_json(fs, RootName.WIZARDS, rel_path)
        cur_fp = fingerprint_json(current)
        new_fp = fingerprint_json(obj)
        if cur_fp != new_fp:
            _store_history_entry(fs, kind=kind, fingerprint=cur_fp, obj=current)

    # Save new file canonically.
    _atomic_write_json(fs, RootName.WIZARDS, rel_path, obj)


def _history_index_path(kind: str) -> str:
    return f"{HISTORY_DIR}/{kind}/index.json"


def _load_history_index(fs: FileService, *, kind: str) -> list[str]:
    path = _history_index_path(kind)
    if not fs.exists(RootName.WIZARDS, path):
        return []
    data = _load_json(fs, RootName.WIZARDS, path)
    if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
        return []
    return list(data)


def _store_history_entry(fs: FileService, *, kind: str, fingerprint: str, obj: Any) -> None:
    rel = f"{HISTORY_DIR}/{kind}/{fingerprint}.json"
    if not fs.exists(RootName.WIZARDS, rel):
        _atomic_write_json(fs, RootName.WIZARDS, rel, obj)

    index = _load_history_index(fs, kind=kind)
    # Deterministic retention: keep most-recent-first, unique.
    index = [fingerprint] + [x for x in index if x != fingerprint]
    index = index[:HISTORY_LIMIT]
    _atomic_write_json(fs, RootName.WIZARDS, _history_index_path(kind), index)


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
