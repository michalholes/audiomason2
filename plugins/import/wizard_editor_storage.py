"""WizardDefinition editor storage helpers (plugin: import).

Provides canonical JSON load/save for WizardDefinition under the WIZARDS root.

Rules:
- canonical JSON (UTF-8, ensure_ascii, sort keys, newline)
- atomic write (temp + rename)
- validate before save

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from plugins.file_io.service import FileService
from plugins.file_io.service.types import RootName

from .fingerprints import fingerprint_json
from .storage import atomic_write_json, atomic_write_json_if_missing, read_json
from .wizard_definition_model import (
    DEFAULT_WIZARD_DEFINITION,
    WIZARD_DEFINITION_REL_PATH,
    canonicalize_wizard_definition,
    migrate_v1_to_v2,
    validate_wizard_definition_structure,
)

WIZARD_DEFINITION_DRAFT_REL_PATH = "import/definitions/wizard_definition.draft.json"

HISTORY_DIR = "import/editor_history"
HISTORY_LIMIT = 5


def canonicalize_to_v2(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError("wizard_definition must be an object")

    wd: dict[str, Any] = obj
    if wd.get("version") == 1:
        wd = migrate_v1_to_v2(wd)

    validate_wizard_definition_structure(wd)
    wd = canonicalize_wizard_definition(wd)

    if wd.get("version") != 2:
        raise ValueError("wizard_definition must be version 2")

    if not isinstance(wd, dict):
        raise ValueError("wizard_definition must be an object")

    return wd


def ensure_wizard_definition_active_exists(fs: FileService) -> dict[str, Any]:
    atomic_write_json_if_missing(
        fs,
        RootName.WIZARDS,
        WIZARD_DEFINITION_REL_PATH,
        DEFAULT_WIZARD_DEFINITION,
    )
    active = read_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH)
    return canonicalize_to_v2(active)


def get_wizard_definition_draft(fs: FileService) -> dict[str, Any]:
    active = ensure_wizard_definition_active_exists(fs)
    if fs.exists(RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_REL_PATH):
        draft = read_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_REL_PATH)
        return canonicalize_to_v2(draft)
    return active


def put_wizard_definition_draft(fs: FileService, obj: Any) -> dict[str, Any]:
    canon = canonicalize_to_v2(obj)
    atomic_write_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_REL_PATH, canon)
    return canon


def reset_wizard_definition_draft(fs: FileService) -> dict[str, Any]:
    canon = canonicalize_to_v2(DEFAULT_WIZARD_DEFINITION)
    atomic_write_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_REL_PATH, canon)
    return canon


def activate_wizard_definition_draft(fs: FileService) -> dict[str, Any]:
    active = ensure_wizard_definition_active_exists(fs)

    if not fs.exists(RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_REL_PATH):
        raise ValueError("wizard_definition draft does not exist")

    draft_any = read_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_REL_PATH)
    draft = canonicalize_to_v2(draft_any)

    cur_fp = fingerprint_json(active)
    new_fp = fingerprint_json(draft)
    if cur_fp != new_fp:
        _store_history_entry(fs, fingerprint=cur_fp, obj=active)
        atomic_write_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH, draft)
        active = draft

    fs.delete_file(RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_REL_PATH)
    return active


def delete_wizard_definition_draft(fs: FileService) -> None:
    if fs.exists(RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_REL_PATH):
        fs.delete_file(RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_REL_PATH)


def load_wizard_definition(fs: FileService) -> Any:
    wd = read_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH)
    return canonicalize_to_v2(wd)


def save_wizard_definition(fs: FileService, obj: Any) -> None:
    canon = canonicalize_to_v2(obj)
    atomic_write_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH, canon)


def save_wizard_definition_with_history(fs: FileService, obj: Any) -> None:
    """Save WizardDefinition ACTIVE and record history deterministically."""

    canon = canonicalize_to_v2(obj)

    if fs.exists(RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH):
        cur = load_wizard_definition(fs)
        cur_fp = fingerprint_json(cur)
        new_fp = fingerprint_json(canon)
        if cur_fp != new_fp:
            _store_history_entry(fs, fingerprint=cur_fp, obj=cur)

    atomic_write_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH, canon)


def reset_wizard_definition(fs: FileService, obj: Any | None = None) -> None:
    if obj is None:
        obj = DEFAULT_WIZARD_DEFINITION
    save_wizard_definition_with_history(fs, obj)


def list_wizard_definition_history(fs: FileService) -> list[str]:
    return list(_load_history_index(fs))


def rollback_wizard_definition(fs: FileService, *, fingerprint: str) -> None:
    rel = f"{HISTORY_DIR}/wizard_definition/{fingerprint}.json"
    obj = read_json(fs, RootName.WIZARDS, rel)
    save_wizard_definition_with_history(fs, obj)


def _history_index_path() -> str:
    return f"{HISTORY_DIR}/wizard_definition/index.json"


def _load_history_index(fs: FileService) -> list[str]:
    path = _history_index_path()
    if not fs.exists(RootName.WIZARDS, path):
        return []
    data = read_json(fs, RootName.WIZARDS, path)
    if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
        return []
    return list(data)


def _store_history_entry(fs: FileService, *, fingerprint: str, obj: Any) -> None:
    rel = f"{HISTORY_DIR}/wizard_definition/{fingerprint}.json"
    if not fs.exists(RootName.WIZARDS, rel):
        atomic_write_json(fs, RootName.WIZARDS, rel, obj)

    index = _load_history_index(fs)
    index = [fingerprint] + [x for x in index if x != fingerprint]
    index = index[:HISTORY_LIMIT]
    atomic_write_json(fs, RootName.WIZARDS, _history_index_path(), index)
