"""Phase II fork/join primitive registry surface for import DSL runtime.

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
        "primitive_id": "parallel.fork_join",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": (
            "deterministic branch_order execution, explicit join_policy, fail_on_conflict merge"
        ),
        "allowed_errors": ["INVARIANT_VIOLATION"],
    }
]


__all__ = ["REGISTRY_ENTRIES"]
