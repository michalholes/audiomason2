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

from .dsl.primitive_registry_storage import (
    bootstrap_primitive_registry_if_missing,
    load_or_bootstrap_primitive_registry,
)
from .dsl.wizard_definition_v3_model import validate_wizard_definition_v3_against_registry
from .fingerprints import fingerprint_json
from .storage import atomic_write_json, atomic_write_json_if_missing, read_json
from .wizard_definition_model import (
    DEFAULT_WIZARD_DEFINITION as _DEFAULT_WIZARD_DEFINITION,
)
from .wizard_definition_model import (
    WIZARD_DEFINITION_REL_PATH,
    _validated_bootstrap_definition,
    canonicalize_wizard_definition,
    migrate_v1_to_v2,
    validate_wizard_definition_constraints_v2,
    validate_wizard_definition_structure,
)

WIZARD_DEFINITION_DRAFT_REL_PATH = "import/definitions/wizard_definition.draft.json"
WIZARD_DEFINITION_DRAFT_META_REL_PATH = "import/definitions/wizard_definition.draft.meta.json"
WIZARD_DEFINITION_DRAFT_QUARANTINE_DIR = "import/definitions/quarantine"

HISTORY_DIR = "import/editor_history"
HISTORY_LIMIT = 5

DEFAULT_WIZARD_DEFINITION = _DEFAULT_WIZARD_DEFINITION


def canonicalize_to_supported(fs: FileService, obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError("wizard_definition must be an object")

    wd: dict[str, Any] = obj
    if wd.get("version") == 1:
        wd = migrate_v1_to_v2(wd)

    validate_wizard_definition_structure(wd)
    wd_any = canonicalize_wizard_definition(wd)

    if not isinstance(wd_any, dict):
        raise ValueError("wizard_definition must be an object")

    wd = wd_any
    ver = wd.get("version")

    if ver == 2:
        validate_wizard_definition_constraints_v2(wd)
        return wd

    if ver == 3:
        registry = load_or_bootstrap_primitive_registry(fs)
        validate_wizard_definition_v3_against_registry(wd, registry)
        return wd

    raise ValueError("wizard_definition must be version 2 or 3")


def ensure_wizard_definition_active_exists(fs: FileService) -> dict[str, Any]:
    bootstrap_primitive_registry_if_missing(fs)

    atomic_write_json_if_missing(
        fs,
        RootName.WIZARDS,
        WIZARD_DEFINITION_REL_PATH,
        _validated_bootstrap_definition(fs, bootstrap_default_version=3),
    )
    active = read_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH)
    try:
        return canonicalize_to_supported(fs, active)
    except Exception:
        canon_default = _validated_bootstrap_definition(fs, bootstrap_default_version=3)
        atomic_write_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH, canon_default)
        return canon_default


def get_wizard_definition_draft(fs: FileService) -> dict[str, Any]:
    active = ensure_wizard_definition_active_exists(fs)
    draft = _load_wizard_definition_draft(fs, active=active, strict=False)
    if draft is None:
        return active
    return draft


def put_wizard_definition_draft(fs: FileService, obj: Any) -> dict[str, Any]:
    active = ensure_wizard_definition_active_exists(fs)
    canon = canonicalize_to_supported(fs, obj)
    atomic_write_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_REL_PATH, canon)
    _write_wizard_definition_draft_lineage(
        fs,
        active_fingerprint=fingerprint_json(active),
    )
    return canon


def reset_wizard_definition_draft(fs: FileService) -> dict[str, Any]:
    active = ensure_wizard_definition_active_exists(fs)
    canon = canonicalize_to_supported(fs, active)
    atomic_write_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_REL_PATH, canon)
    _write_wizard_definition_draft_lineage(
        fs,
        active_fingerprint=fingerprint_json(active),
    )
    return canon


def activate_wizard_definition_draft(fs: FileService) -> dict[str, Any]:
    active = ensure_wizard_definition_active_exists(fs)

    if not fs.exists(RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_REL_PATH):
        raise ValueError("wizard_definition draft does not exist")

    draft = _load_wizard_definition_draft(fs, active=active, strict=True)
    if draft is None:
        raise ValueError("wizard_definition draft is stale")

    cur_fp = fingerprint_json(active)
    new_fp = fingerprint_json(draft)
    if cur_fp != new_fp:
        _store_history_entry(fs, fingerprint=cur_fp, obj=active)
        atomic_write_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH, draft)
        active = draft

    delete_wizard_definition_draft(fs)
    return active


def delete_wizard_definition_draft(fs: FileService) -> None:
    if fs.exists(RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_REL_PATH):
        fs.delete_file(RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_REL_PATH)
    if fs.exists(RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_META_REL_PATH):
        fs.delete_file(RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_META_REL_PATH)


def _wizard_definition_draft_quarantine_paths(
    *,
    source_active_fingerprint: str | None,
    current_active_fingerprint: str,
    draft_fingerprint: str,
) -> tuple[str, str]:
    source_label = source_active_fingerprint or "nometa"
    base = (
        f"{WIZARD_DEFINITION_DRAFT_QUARANTINE_DIR}/"
        f"wizard_definition.draft.stale."
        f"{source_label}.{current_active_fingerprint}.{draft_fingerprint}"
    )
    return (
        f"{base}.json",
        f"{base}.meta.json",
    )


def _read_wizard_definition_draft_lineage(fs: FileService) -> str | None:
    if not fs.exists(RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_META_REL_PATH):
        return None
    data = read_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_META_REL_PATH)
    if not isinstance(data, dict):
        return None
    value = data.get("source_active_fingerprint")
    if not isinstance(value, str) or not value:
        return None
    return value


def _write_wizard_definition_draft_lineage(
    fs: FileService,
    *,
    active_fingerprint: str,
) -> None:
    atomic_write_json(
        fs,
        RootName.WIZARDS,
        WIZARD_DEFINITION_DRAFT_META_REL_PATH,
        {"source_active_fingerprint": active_fingerprint},
    )


def _quarantine_wizard_definition_draft(
    fs: FileService,
    *,
    source_active_fingerprint: str | None,
    current_active_fingerprint: str,
    draft_fingerprint: str,
    reason: str,
) -> None:
    draft_rel, meta_rel = _wizard_definition_draft_quarantine_paths(
        source_active_fingerprint=source_active_fingerprint,
        current_active_fingerprint=current_active_fingerprint,
        draft_fingerprint=draft_fingerprint,
    )
    if fs.exists(RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_REL_PATH):
        fs.rename(
            RootName.WIZARDS,
            WIZARD_DEFINITION_DRAFT_REL_PATH,
            draft_rel,
            overwrite=True,
        )
    if fs.exists(RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_META_REL_PATH):
        fs.delete_file(RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_META_REL_PATH)
    atomic_write_json(
        fs,
        RootName.WIZARDS,
        meta_rel,
        {
            "current_active_fingerprint": current_active_fingerprint,
            "draft_fingerprint": draft_fingerprint,
            "reason": reason,
            "source_active_fingerprint": source_active_fingerprint,
        },
    )


def _load_wizard_definition_draft(
    fs: FileService,
    *,
    active: dict[str, Any],
    strict: bool,
) -> dict[str, Any] | None:
    if not fs.exists(RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_REL_PATH):
        return None

    draft_any = read_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_DRAFT_REL_PATH)
    draft = canonicalize_to_supported(fs, draft_any)
    active_fingerprint = fingerprint_json(active)
    draft_fingerprint = fingerprint_json(draft)
    source_active_fingerprint = _read_wizard_definition_draft_lineage(fs)

    if draft_fingerprint == active_fingerprint:
        _write_wizard_definition_draft_lineage(
            fs,
            active_fingerprint=active_fingerprint,
        )
        return draft

    if source_active_fingerprint != active_fingerprint:
        reason = "stale_lineage"
        if source_active_fingerprint is None:
            reason = "missing_lineage_mismatch"
        _quarantine_wizard_definition_draft(
            fs,
            source_active_fingerprint=source_active_fingerprint,
            current_active_fingerprint=active_fingerprint,
            draft_fingerprint=draft_fingerprint,
            reason=reason,
        )
        if strict:
            raise ValueError("wizard_definition draft is stale")
        return None

    return draft


def load_wizard_definition(fs: FileService) -> Any:
    wd = read_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH)
    return canonicalize_to_supported(fs, wd)


def save_wizard_definition(fs: FileService, obj: Any) -> None:
    canon = canonicalize_to_supported(fs, obj)
    atomic_write_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH, canon)


def save_wizard_definition_with_history(fs: FileService, obj: Any) -> None:
    """Save WizardDefinition ACTIVE and record history deterministically."""

    canon = canonicalize_to_supported(fs, obj)

    if fs.exists(RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH):
        cur = load_wizard_definition(fs)
        cur_fp = fingerprint_json(cur)
        new_fp = fingerprint_json(canon)
        if cur_fp != new_fp:
            _store_history_entry(fs, fingerprint=cur_fp, obj=cur)

    atomic_write_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH, canon)


def reset_wizard_definition(fs: FileService, obj: Any | None = None) -> None:
    if obj is None:
        obj = _validated_bootstrap_definition(fs, bootstrap_default_version=3)
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
