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
from typing import Protocol, TypeGuard, cast, runtime_checkable

from plugins.file_io.service import FileService, RootName

from .fingerprints import fingerprint_json
from .flow_config_defaults import DEFAULT_FLOW_CONFIG
from .flow_config_validation import normalize_flow_config
from .step_catalog import build_step_catalog_projection
from .wizard_definition_model import build_effective_workflow_snapshot
from .wizard_editor_storage import ensure_wizard_definition_active_exists

FLOW_CONFIG_REL_PATH = "import/config/flow_config.json"
FLOW_CONFIG_DRAFT_REL_PATH = "import/config/flow_config.draft.json"

HISTORY_DIR = "import/editor_history"
HISTORY_LIMIT = 5


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


@runtime_checkable
class _Flushable(Protocol):
    def flush(self) -> None: ...


@runtime_checkable
class _HasFileno(Protocol):
    def fileno(self) -> int: ...


def _derived_editor_catalog(fs: FileService) -> dict[str, object]:
    wizard_definition = ensure_wizard_definition_active_exists(fs)
    flow_config = ensure_flow_config_active_exists(fs)
    projection = build_step_catalog_projection(
        wizard_definition=wizard_definition,
        flow_config=flow_config,
    )
    steps: list[dict[str, object]] = [
        {
            "step_id": step_id,
            "title": str(entry.get("title") or step_id),
            "computed_only": False,
            "fields": [],
        }
        for step_id, entry in sorted(projection.items())
    ]
    return {"version": 1, "steps": steps}


def _derived_editor_flow(fs: FileService) -> dict[str, object]:
    wizard_definition = ensure_wizard_definition_active_exists(fs)
    flow_config = ensure_flow_config_active_exists(fs)
    step_order = build_effective_workflow_snapshot(
        wizard_definition=wizard_definition,
        flow_config=flow_config,
    )
    return {
        "version": 1,
        "entry_step_id": step_order[0],
        "nodes": [
            {
                "step_id": sid,
                "next_step_id": step_order[index + 1] if index + 1 < len(step_order) else None,
                "prev_step_id": step_order[index - 1] if index > 0 else None,
            }
            for index, sid in enumerate(step_order)
        ],
    }


def load_catalog(fs: FileService) -> object:
    return _derived_editor_catalog(fs)


def load_flow(fs: FileService) -> object:
    return _derived_editor_flow(fs)


def save_catalog(fs: FileService, obj: object) -> None:
    raise ValueError("catalog is immutable; editor may only modify flow_config")


def save_flow(fs: FileService, obj: object) -> None:
    raise ValueError("flow is immutable; editor may only modify flow_config")


def load_flow_config(fs: FileService) -> object:
    return _load_json(fs, RootName.WIZARDS, FLOW_CONFIG_REL_PATH)


def save_flow_config(fs: FileService, obj: object) -> None:
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


def _strip_legacy_ui(obj: object) -> object:
    if _is_str_object_dict(obj) and "ui" in obj:
        out = dict(obj)
        out.pop("ui", None)
        return out
    return obj


def ensure_flow_config_active_exists(fs: FileService) -> dict[str, object]:
    if not fs.exists(RootName.WIZARDS, FLOW_CONFIG_REL_PATH):
        boot = _strip_legacy_ui(DEFAULT_FLOW_CONFIG)
        canon = normalize_flow_config(boot)
        _atomic_write_json(fs, RootName.WIZARDS, FLOW_CONFIG_REL_PATH, canon)
        return canon

    raw = _load_json(fs, RootName.WIZARDS, FLOW_CONFIG_REL_PATH)
    had_ui = _is_str_object_dict(raw) and "ui" in raw
    cfg = normalize_flow_config(_strip_legacy_ui(raw))

    if had_ui:
        _atomic_write_json(fs, RootName.WIZARDS, FLOW_CONFIG_REL_PATH, cfg)

    return cfg


def get_flow_config_draft(fs: FileService) -> dict[str, object]:
    active = ensure_flow_config_active_exists(fs)
    if fs.exists(RootName.WIZARDS, FLOW_CONFIG_DRAFT_REL_PATH):
        draft_any = _load_json(fs, RootName.WIZARDS, FLOW_CONFIG_DRAFT_REL_PATH)
        draft_any = _strip_legacy_ui(draft_any)
        return normalize_flow_config(draft_any)
    return active


def put_flow_config_draft(fs: FileService, obj: object) -> dict[str, object]:
    canon = normalize_flow_config(obj)
    _atomic_write_json(fs, RootName.WIZARDS, FLOW_CONFIG_DRAFT_REL_PATH, canon)
    return canon


def reset_flow_config_draft(fs: FileService) -> dict[str, object]:
    canon = normalize_flow_config(_strip_legacy_ui(DEFAULT_FLOW_CONFIG))
    _atomic_write_json(fs, RootName.WIZARDS, FLOW_CONFIG_DRAFT_REL_PATH, canon)
    return canon


def activate_flow_config_draft(fs: FileService) -> dict[str, object]:
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


def _load_json(fs: FileService, root: RootName, rel_path: str) -> object:
    with fs.open_read(root, rel_path) as f:
        data = f.read()
    return cast(object, json.loads(data.decode("utf-8")))


def _atomic_write_json(fs: FileService, root: RootName, rel_path: str, obj: object) -> None:
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


def _save_with_history(fs: FileService, *, kind: str, rel_path: str, obj: object) -> None:
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
    if not _is_object_list(data) or not all(isinstance(x, str) for x in data):
        return []
    return [x for x in data if isinstance(x, str)]


def _store_history_entry(fs: FileService, *, kind: str, fingerprint: str, obj: object) -> None:
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


def _best_effort_fsync(f: object) -> None:
    try:
        if isinstance(f, _Flushable):
            f.flush()
        if isinstance(f, _HasFileno):
            os.fsync(f.fileno())
    except Exception:
        return
