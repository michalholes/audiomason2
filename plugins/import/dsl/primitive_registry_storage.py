"""Primitive registry storage helpers (import plugin).

This module owns the runtime artifact:
  wizards/import/definitions/primitive_registry.json

The registry is bootstrapped if missing and is canonicalized on load.

ASCII-only.
"""

from __future__ import annotations

from typing import TypeGuard, cast

from plugins.file_io.service import FileService
from plugins.file_io.service.types import RootName

from ..storage import atomic_write_json, atomic_write_json_if_missing, read_json
from .primitive_registry_model import canonicalize_primitive_registry, validate_primitive_registry

REL_PATH = "import/definitions/primitive_registry.json"


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _default_schema_object() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {},
        "required": [],
        "description": "",
    }


def _default_primitives() -> list[dict[str, object]]:
    from ..primitives import baseline_registry_entries

    out: list[dict[str, object]] = []
    for entry in baseline_registry_entries():
        item = dict(entry)
        item.setdefault("inputs_schema", _default_schema_object())
        item.setdefault("outputs_schema", _default_schema_object())
        out.append(item)
    return out


DEFAULT_REGISTRY: dict[str, object] = {
    "registry_version": 1,
    "primitives": _default_primitives(),
}


def _merge_required_primitives(registry: dict[str, object]) -> dict[str, object]:
    prims_any = registry.get("primitives")
    if _is_object_list(prims_any):
        primitives = [dict(item) for item in prims_any if _is_str_object_dict(item)]
    else:
        primitives = []
    seen: set[tuple[str, int]] = set()
    for item in primitives:
        primitive_id = item.get("primitive_id")
        version = item.get("version")
        if isinstance(primitive_id, str) and isinstance(version, int):
            seen.add((primitive_id, version))

    for entry in _default_primitives():
        version_any = entry.get("version")
        version = version_any if isinstance(version_any, int) else 0
        key = (str(entry.get("primitive_id") or ""), version)
        if key not in seen:
            primitives.append(entry)
            seen.add(key)

    out = _as_str_object_dict(registry)
    out["primitives"] = primitives
    return out


def _canonicalize_validated_registry(obj: object) -> dict[str, object]:
    reg = validate_primitive_registry(obj)
    canon_any = canonicalize_primitive_registry(_merge_required_primitives(reg))
    if not _is_str_object_dict(canon_any):
        raise ValueError("primitive registry must be an object")
    return validate_primitive_registry(dict(canon_any))


def bootstrap_primitive_registry_if_missing(fs: FileService) -> bool:
    return atomic_write_json_if_missing(
        fs,
        RootName.WIZARDS,
        REL_PATH,
        _canonicalize_validated_registry(DEFAULT_REGISTRY),
    )


def load_primitive_registry(fs: FileService) -> dict[str, object]:
    reg_any = read_json(fs, RootName.WIZARDS, REL_PATH)
    return _canonicalize_validated_registry(reg_any)


def load_or_bootstrap_primitive_registry(fs: FileService) -> dict[str, object]:
    bootstrap_primitive_registry_if_missing(fs)

    try:
        reg = load_primitive_registry(fs)
    except Exception:
        reg = _canonicalize_validated_registry(DEFAULT_REGISTRY)
    atomic_write_json(fs, RootName.WIZARDS, REL_PATH, reg)
    return reg


def save_primitive_registry(fs: FileService, obj: object) -> dict[str, object]:
    canon = _canonicalize_validated_registry(obj)
    atomic_write_json(fs, RootName.WIZARDS, REL_PATH, canon)
    return canon
