"""Baseline v1 data primitives for import DSL runtime.

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
        "primitive_id": "data.set",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": [],
    },
    {
        "primitive_id": "data.unset",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": [],
    },
    {
        "primitive_id": "data.filter",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": [],
    },
    {
        "primitive_id": "data.map",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": [],
    },
    {
        "primitive_id": "data.group_by",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": [],
    },
    {
        "primitive_id": "data.sort",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": [],
    },
    {
        "primitive_id": "data.format",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": [],
    },
]


def execute(primitive_id: str, primitive_version: int, inputs: dict[str, Any]) -> dict[str, Any]:
    if primitive_version != 1:
        raise ValueError("unsupported primitive version")
    if primitive_id == "data.set":
        return {"value": inputs.get("value")}
    if primitive_id == "data.unset":
        return {}
    if primitive_id == "data.filter":
        items = inputs.get("items")
        if isinstance(items, list):
            return {"items": list(items)}
        return {"items": []}
    if primitive_id == "data.map":
        items = inputs.get("items")
        if isinstance(items, list):
            return {"items": list(items)}
        return {"items": []}
    if primitive_id == "data.group_by":
        items = inputs.get("items")
        if isinstance(items, list):
            return {"groups": {"default": list(items)}}
        return {"groups": {}}
    if primitive_id == "data.sort":
        items = inputs.get("items")
        if isinstance(items, list):
            try:
                return {"items": sorted(items)}
            except Exception:
                return {"items": list(items)}
        return {"items": []}
    if primitive_id == "data.format":
        template = inputs.get("template")
        if isinstance(template, str):
            return {"value": template}
        return {"value": ""}
    raise ValueError("unknown data primitive")
