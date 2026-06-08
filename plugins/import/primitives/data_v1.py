"""Baseline v1 data primitives for import DSL runtime.

ASCII-only.
"""

from __future__ import annotations

from typing import TypeGuard

from ..dsl.expr_eval import eval_expr_ref
from ..engine_util import parse_selection_expr


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_str_list(value: object) -> list[str]:
    if not _is_object_list(value):
        return []
    return [item for item in value if isinstance(item, str)]


def _selected_ids_from_selection(*, ordered: list[str], selection: object) -> list[str]:
    if not ordered:
        return []

    if selection is None:
        return list(ordered)

    if isinstance(selection, int) and not isinstance(selection, bool):
        if 1 <= selection <= len(ordered):
            return [ordered[selection - 1]]
        return []

    ordered_set = set(ordered)
    if _is_object_list(selection):
        values = list(selection)
        if all(isinstance(item, str) for item in values):
            requested_ids = [str(item) for item in values]
            if not all(item in ordered_set for item in requested_ids):
                return []
            requested_set = set(requested_ids)
            return [item_id for item_id in ordered if item_id in requested_set]
        if all(isinstance(item, int) and not isinstance(item, bool) for item in values):
            requested_indices = {
                item
                for item in values
                if isinstance(item, int) and not isinstance(item, bool) and item > 0
            }
            return [
                item_id
                for index, item_id in enumerate(ordered, start=1)
                if index in requested_indices
            ]
        return []

    expr = str(selection).strip() if isinstance(selection, str) else ""
    if not expr:
        expr = "all"
    try:
        indices = parse_selection_expr(expr, max_index=len(ordered))
    except ValueError:
        return []
    return [ordered[i - 1] for i in indices if 1 <= i <= len(ordered)]


def _sort_key(value: object) -> str:
    return str(value)


def _group_key_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return "null"
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
        result: list[object] = []
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
        mapped: list[object] = []
        for item in items:
            ok, value = _eval_item_expr(value_expr, item=item, state=_state)
            if ok:
                mapped.append(value)
        return {"items": mapped}
    if primitive_id == "source.resolve_selection":
        ordered = _as_str_list(inputs.get("ordered_ids"))
        selected_ids = _selected_ids_from_selection(
            ordered=ordered,
            selection=inputs.get("selection_expr"),
        )
        return {"selected_ids": selected_ids}
    if primitive_id == "data.group_by":
        items_any = inputs.get("items")
        if not _is_object_list(items_any):
            return {"groups": {}, "keys": [], "group_items": []}

        items = list(items_any)
        key_expr = inputs.get("key_expr")
        value_expr = inputs.get("value_expr")
        groups: dict[str, list[object]] = {}
        ordered_keys: list[str] = []

        for item in items:
            key_value: object = item
            if key_expr is not None:
                ok_key, evaluated_key = _eval_item_expr(key_expr, item=item, state=_state)
                if not ok_key:
                    continue
                key_value = evaluated_key

            grouped_value: object = item
            if value_expr is not None:
                ok_value, evaluated_value = _eval_item_expr(value_expr, item=item, state=_state)
                if not ok_value:
                    continue
                grouped_value = evaluated_value

            key_text = _group_key_text(key_value)
            bucket = groups.get(key_text)
            if bucket is None:
                bucket = []
                groups[key_text] = bucket
                ordered_keys.append(key_text)
            bucket.append(grouped_value)

        group_items = [{"key": key, "items": groups[key]} for key in ordered_keys]
        return {
            "groups": groups,
            "keys": ordered_keys,
            "group_items": group_items,
        }
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
