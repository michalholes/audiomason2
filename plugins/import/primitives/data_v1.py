"""Baseline v1 data primitives for import DSL runtime.

ASCII-only.
"""

from __future__ import annotations

from typing import TypeGuard

from ..dsl.expr_eval import eval_expr_ref
from ..engine_util import _parse_selection_expr


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_str_list(value: object) -> list[str]:
    if not _is_object_list(value):
        return []
    return [item for item in value if isinstance(item, str)]


def _sort_key(value: object) -> str:
    return str(value)


def _object_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {},
        "required": [],
        "description": "",
    }


REGISTRY_ENTRIES: list[dict[str, object]] = [
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
    expr_ref: object,
    *,
    item: object,
    state: dict[str, object],
) -> tuple[bool, object]:
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
    inputs: dict[str, object],
    state: dict[str, object] | None = None,
) -> dict[str, object]:
    if primitive_version != 1:
        raise ValueError("unsupported primitive version")
    _state: dict[str, object] = state if isinstance(state, dict) else {}
    if primitive_id == "data.set":
        return {"value": inputs.get("value")}
    if primitive_id == "data.unset":
        return {}
    if primitive_id == "data.filter":
        items_any = inputs.get("items")
        if not _is_object_list(items_any):
            return {"items": []}
        items = list(items_any)
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
        items_any = inputs.get("items")
        if not _is_object_list(items_any):
            return {"items": []}
        items = list(items_any)
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
        ordered = _as_str_list(inputs.get("ordered_ids"))
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
        items_any = inputs.get("items")
        if _is_object_list(items_any):
            items = list(items_any)
            return {"groups": {"default": list(items)}}
        return {"groups": {}}
    if primitive_id == "data.sort":
        items_any = inputs.get("items")
        if _is_object_list(items_any):
            items = list(items_any)
            try:
                return {"items": sorted(items, key=_sort_key)}
            except Exception:
                return {"items": list(items)}
        return {"items": []}
    if primitive_id == "data.format":
        template = inputs.get("template")
        if isinstance(template, str):
            return {"value": template}
        return {"value": ""}
    raise ValueError("unknown data primitive")
