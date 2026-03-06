"""Baseline v1 parallel primitives for import DSL runtime.

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
        "primitive_id": "parallel.map",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": ["INVARIANT_VIOLATION"],
    }
]


def execute(primitive_id: str, primitive_version: int, inputs: dict[str, Any]) -> dict[str, Any]:
    if primitive_id != "parallel.map" or primitive_version != 1:
        raise ValueError("unknown parallel primitive")
    merge_mode = inputs.get("merge_mode", "fail_on_conflict")
    if merge_mode != "fail_on_conflict":
        raise RuntimeError("parallel.map@1 merge_mode must be fail_on_conflict")
    items = inputs.get("items")
    if isinstance(items, list):
        return {"items": list(items), "merge_mode": merge_mode}
    return {"items": [], "merge_mode": merge_mode}
