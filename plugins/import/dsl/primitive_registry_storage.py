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
    # Default registry maps UI step_ids to phase-1 primitives.
    from ..step_catalog import STEP_CATALOG

    out: list[dict[str, Any]] = []
    for step_id in sorted(STEP_CATALOG.keys()):
        out.append(
            {
                "primitive_id": str(step_id),
                "version": 1,
                "phase": 1,
                "inputs_schema": _default_schema_object(),
                "outputs_schema": _default_schema_object(),
                "determinism_notes": "deterministic",
                "allowed_errors": [],
            }
        )
    return out


DEFAULT_REGISTRY: dict[str, Any] = {
    "registry_version": 1,
    "primitives": _default_primitives(),
}


def bootstrap_primitive_registry_if_missing(fs: FileService) -> bool:
    return atomic_write_json_if_missing(
        fs,
        RootName.WIZARDS,
        REL_PATH,
        DEFAULT_REGISTRY,
    )


def load_primitive_registry(fs: FileService) -> dict[str, Any]:
    reg_any = read_json(fs, RootName.WIZARDS, REL_PATH)
    reg = validate_primitive_registry(reg_any)
    canon_any = canonicalize_primitive_registry(reg)
    if not isinstance(canon_any, dict):
        return reg
    return canon_any


def load_or_bootstrap_primitive_registry(fs: FileService) -> dict[str, Any]:
    bootstrap_primitive_registry_if_missing(fs)

    reg = load_primitive_registry(fs)
    # Self-heal ordering-only diffs.
    atomic_write_json(fs, RootName.WIZARDS, REL_PATH, reg)
    return reg


def save_primitive_registry(fs: FileService, obj: Any) -> dict[str, Any]:
    reg = validate_primitive_registry(obj)
    canon_any = canonicalize_primitive_registry(reg)
    if not isinstance(canon_any, dict):
        raise ValueError("primitive registry must be an object")
    atomic_write_json(fs, RootName.WIZARDS, REL_PATH, canon_any)
    return canon_any
