"""Phase II subflow primitive registry surface for import DSL runtime.

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
        "primitive_id": "flow.invoke",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": (
            "deterministic library lookup and explicit parameter binding by name"
        ),
        "allowed_errors": ["INVARIANT_VIOLATION"],
    }
]


__all__ = ["REGISTRY_ENTRIES"]
