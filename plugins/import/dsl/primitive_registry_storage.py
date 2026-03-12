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


def _canonicalize_validated_registry(obj: Any) -> dict[str, Any]:
    reg = validate_primitive_registry(obj)
    canon_any = canonicalize_primitive_registry(reg)
    if not isinstance(canon_any, dict):
        raise ValueError("primitive registry must be an object")
    return canon_any


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

    reg = load_primitive_registry(fs)
    # Self-heal ordering-only diffs.
    atomic_write_json(fs, RootName.WIZARDS, REL_PATH, reg)
    return reg


def save_primitive_registry(fs: FileService, obj: Any) -> dict[str, Any]:
    canon = _canonicalize_validated_registry(obj)
    atomic_write_json(fs, RootName.WIZARDS, REL_PATH, canon)
    return canon
