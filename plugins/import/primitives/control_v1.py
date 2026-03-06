"""Baseline v1 control primitives for import DSL runtime.

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
        "primitive_id": "ctrl.if",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": [],
    },
    {
        "primitive_id": "ctrl.switch",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": [],
    },
    {
        "primitive_id": "ctrl.guard",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": ["INVARIANT_VIOLATION"],
    },
    {
        "primitive_id": "ctrl.stop",
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
    if primitive_id == "ctrl.guard" and inputs.get("allow") is False:
        raise RuntimeError("ctrl.guard blocked execution")
    if primitive_id in {"ctrl.if", "ctrl.switch", "ctrl.guard", "ctrl.stop"}:
        return {}
    raise ValueError("unknown control primitive")
