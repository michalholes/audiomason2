"""Baseline v1 IO primitives for import DSL runtime.

ASCII-only.
"""

from __future__ import annotations

from typing import Any


def _object_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {},
        "required": [],
        "description": "",
    }


REGISTRY_ENTRIES: list[dict[str, Any]] = [
    {
        "primitive_id": "io.list",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": ["VALIDATION_ERROR"],
    },
    {
        "primitive_id": "io.stat",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": ["VALIDATION_ERROR"],
    },
    {
        "primitive_id": "io.read_meta",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": ["VALIDATION_ERROR"],
    },
]


def _validate_ref(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("resolver-friendly ref must be str")
    if value.startswith("/") or value.startswith("\\"):
        raise ValueError("absolute refs are forbidden")
    if ":" in value.split("/", 1)[0]:
        return value
    return value


def execute(primitive_id: str, primitive_version: int, inputs: dict[str, Any]) -> dict[str, Any]:
    if primitive_version != 1:
        raise ValueError("unsupported primitive version")
    ref = _validate_ref(inputs.get("ref", "")) if "ref" in inputs else ""
    if primitive_id == "io.list":
        return {"items": [], "ref": ref}
    if primitive_id == "io.stat":
        return {"ref": ref}
    if primitive_id == "io.read_meta":
        return {"ref": ref, "meta": {}}
    raise ValueError("unknown io primitive")
