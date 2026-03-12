"""Primitive registry storage helpers (import plugin).

This module owns the runtime artifact:
  wizards/import/definitions/primitive_registry.json

The registry is bootstrapped if missing and is canonicalized on load.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from plugins.file_io.service import FileService
from plugins.file_io.service.types import RootName

from ..storage import atomic_write_json, atomic_write_json_if_missing, read_json
from .primitive_registry_model import canonicalize_primitive_registry, validate_primitive_registry

REL_PATH = "import/definitions/primitive_registry.json"


def _default_schema_object() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {},
        "required": [],
        "description": "",
    }


def _default_primitives() -> list[dict[str, Any]]:
    from ..primitives import baseline_registry_entries

    out: list[dict[str, Any]] = []
    for entry in baseline_registry_entries():
        item = dict(entry)
        item.setdefault("inputs_schema", _default_schema_object())
        item.setdefault("outputs_schema", _default_schema_object())
        out.append(item)
    return out


DEFAULT_REGISTRY: dict[str, Any] = {
    "registry_version": 1,
    "primitives": _default_primitives(),
}


def _merge_required_primitives(registry: dict[str, Any]) -> dict[str, Any]:
    prims_any = registry.get("primitives")
    primitives = list(prims_any) if isinstance(prims_any, list) else []
    seen: set[tuple[str, int]] = set()
    for item in primitives:
        if not isinstance(item, dict):
            continue
        primitive_id = item.get("primitive_id")
        version = item.get("version")
        if isinstance(primitive_id, str) and isinstance(version, int):
            seen.add((primitive_id, version))

    for entry in _default_primitives():
        key = (str(entry.get("primitive_id") or ""), int(entry.get("version") or 0))
        if key not in seen:
            primitives.append(entry)
            seen.add(key)

    out = dict(registry)
    out["primitives"] = primitives
    return out


def _canonicalize_validated_registry(obj: Any) -> dict[str, Any]:
    reg = validate_primitive_registry(obj)
    canon_any = canonicalize_primitive_registry(_merge_required_primitives(reg))
    if not isinstance(canon_any, dict):
        raise ValueError("primitive registry must be an object")
    return validate_primitive_registry(canon_any)


def bootstrap_primitive_registry_if_missing(fs: FileService) -> bool:
    return atomic_write_json_if_missing(
        fs,
        RootName.WIZARDS,
        REL_PATH,
        _canonicalize_validated_registry(DEFAULT_REGISTRY),
    )


def load_primitive_registry(fs: FileService) -> dict[str, Any]:
    reg_any = read_json(fs, RootName.WIZARDS, REL_PATH)
    return _canonicalize_validated_registry(reg_any)


def load_or_bootstrap_primitive_registry(fs: FileService) -> dict[str, Any]:
    bootstrap_primitive_registry_if_missing(fs)

    try:
        reg = load_primitive_registry(fs)
    except Exception:
        reg = _canonicalize_validated_registry(DEFAULT_REGISTRY)
    atomic_write_json(fs, RootName.WIZARDS, REL_PATH, reg)
    return reg


def save_primitive_registry(fs: FileService, obj: Any) -> dict[str, Any]:
    canon = _canonicalize_validated_registry(obj)
    atomic_write_json(fs, RootName.WIZARDS, REL_PATH, canon)
    return canon
