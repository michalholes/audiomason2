"""Baseline v1 data primitives for import DSL runtime.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from ..dsl.expr_eval import eval_expr_ref
from ..engine_util import _parse_selection_expr


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
        "primitive_id": "source.resolve_selection",
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


def _eval_item_expr(
    expr_ref: Any,
    *,
    item: Any,
    state: dict[str, Any],
) -> tuple[bool, Any]:
    """Evaluate an expr_ref with $.inputs.item bound to the current item."""
    ok, value, _err = eval_expr_ref(
        expr_ref,
        state=state,
        inputs={"item": item},
    )
    return ok, value


def execute(
    primitive_id: str,
    primitive_version: int,
    inputs: dict[str, Any],
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if primitive_version != 1:
        raise ValueError("unsupported primitive version")
    _state: dict[str, Any] = state if isinstance(state, dict) else {}
    if primitive_id == "data.set":
        return {"value": inputs.get("value")}
    if primitive_id == "data.unset":
        return {}
    if primitive_id == "data.filter":
        items = inputs.get("items")
        if not isinstance(items, list):
            return {"items": []}
        condition_expr = inputs.get("condition_expr")
        if condition_expr is None:
            return {"items": list(items)}
        result = []
        for item in items:
            ok, value = _eval_item_expr(condition_expr, item=item, state=_state)
            if ok and value is True:
                result.append(item)
        return {"items": result}
    if primitive_id == "data.map":
        items = inputs.get("items")
        if not isinstance(items, list):
            return {"items": []}
        value_expr = inputs.get("value_expr")
        if value_expr is None:
            return {"items": list(items)}
        result = []
        for item in items:
            ok, value = _eval_item_expr(value_expr, item=item, state=_state)
            if ok:
                result.append(value)
        return {"items": result}
    if primitive_id == "source.resolve_selection":
        ordered_any = inputs.get("ordered_ids")
        ordered = [
            x for x in (ordered_any if isinstance(ordered_any, list) else [])
            if isinstance(x, str)
        ]
        expr_raw = inputs.get("selection_expr")
        expr = str(expr_raw).strip() if isinstance(expr_raw, str) else "all"
        if not expr:
            expr = "all"
        try:
            indices = _parse_selection_expr(expr, max_index=len(ordered))
        except ValueError:
            return {"selected_ids": []}
        return {"selected_ids": [ordered[i - 1] for i in indices if 1 <= i <= len(ordered)]}
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
