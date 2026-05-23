"""Baseline v1 UI primitives for import DSL runtime.

ASCII-only.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import TypeGuard, cast


def _object_schema(*, required: list[str] | None = None) -> dict[str, object]:
    return {
        "type": "object",
        "properties": {},
        "required": list(required or []),
        "description": "",
    }


REGISTRY_ENTRIES: list[dict[str, object]] = [
    {
        "primitive_id": "ui.message",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": [],
    },
    {
        "primitive_id": "ui.prompt_text",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(required=["value"]),
        "determinism_notes": "deterministic",
        "allowed_errors": ["VALIDATION_ERROR"],
    },
    {
        "primitive_id": "ui.prompt_select",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(required=["selection"]),
        "determinism_notes": "deterministic",
        "allowed_errors": ["VALIDATION_ERROR"],
    },
    {
        "primitive_id": "ui.prompt_confirm",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(required=["confirmed"]),
        "determinism_notes": "deterministic",
        "allowed_errors": ["VALIDATION_ERROR"],
    },
]


PROMPT_IDS: set[str] = {
    "ui.prompt_text",
    "ui.prompt_select",
    "ui.prompt_confirm",
}


OUTPUT_KEYS: dict[str, str] = {
    "ui.prompt_text": "value",
    "ui.prompt_select": "selection",
    "ui.prompt_confirm": "confirmed",
}


PROMPT_RENDERER_METADATA_KEYS: tuple[str, ...] = (
    "label",
    "prompt",
    "help",
    "hint",
    "examples",
)
PROMPT_RENDERER_EXPR_METADATA_KEYS: tuple[str, ...] = (
    "label_expr",
    "prompt_expr",
    "help_expr",
    "hint_expr",
    "examples_expr",
)
PROMPT_RUNTIME_METADATA_KEYS: tuple[str, ...] = (
    "default_value",
    "prefill",
    "default_expr",
    "prefill_expr",
    "autofill_if",
)
PROMPT_METADATA_KEYS: tuple[str, ...] = (
    *PROMPT_RENDERER_METADATA_KEYS,
    *PROMPT_RENDERER_EXPR_METADATA_KEYS,
    *PROMPT_RUNTIME_METADATA_KEYS,
)
_EXPR_METADATA_KEYS: tuple[str, ...] = (
    *PROMPT_RENDERER_EXPR_METADATA_KEYS,
    "default_expr",
    "prefill_expr",
    "autofill_if",
)


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_expr_ref(value: object) -> bool:
    return (
        _is_str_object_dict(value)
        and set(value.keys()) == {"expr"}
        and isinstance(value.get("expr"), str)
    )


def is_prompt_primitive(primitive_id: str, primitive_version: int) -> bool:
    return primitive_version == 1 and primitive_id in PROMPT_IDS


def prompt_output_key(primitive_id: str, primitive_version: int) -> str | None:
    if primitive_version != 1:
        return None
    return OUTPUT_KEYS.get(primitive_id)


def project_prompt_ui(
    primitive_id: str,
    primitive_version: int,
    inputs: dict[str, object],
) -> dict[str, object] | None:
    if not is_prompt_primitive(primitive_id, primitive_version):
        return None
    out: dict[str, object] = {}
    for key in PROMPT_METADATA_KEYS:
        if key in inputs:
            value = inputs[key]
            if key in _EXPR_METADATA_KEYS and not _is_expr_ref(value):
                raise ValueError(f"{primitive_id}@1 {key} must be ExprRef")
            out[key] = deepcopy(value)
    return out


def normalize_prompt_ui(
    primitive_id: str,
    primitive_version: int,
    metadata: dict[str, object],
    *,
    resolve_expr: Callable[[dict[str, object], str, dict[str, object]], object],
    path_prefix: str,
) -> dict[str, object]:
    if not is_prompt_primitive(primitive_id, primitive_version):
        return {}

    normalized: dict[str, object] = {}
    for key in PROMPT_RENDERER_METADATA_KEYS:
        if key in metadata:
            normalized[key] = deepcopy(metadata[key])
    for key, target_key in (
        ("label_expr", "label"),
        ("prompt_expr", "prompt"),
        ("help_expr", "help"),
        ("hint_expr", "hint"),
        ("examples_expr", "examples"),
    ):
        if key not in metadata:
            continue
        expr_ref = metadata[key]
        if not _is_str_object_dict(expr_ref):
            raise ValueError(f"{primitive_id}@1 {key} must be ExprRef")
        value = resolve_expr(
            expr_ref,
            f"{path_prefix}.{key}",
            normalized,
        )
        if target_key == "examples":
            if not _is_object_list(value):
                raise ValueError(f"{primitive_id}@1 {key} must resolve to list")
            normalized[target_key] = [item for item in value]
        else:
            if not isinstance(value, str):
                raise ValueError(f"{primitive_id}@1 {key} must resolve to string")
            normalized[target_key] = value
    if "default_value" in metadata:
        normalized["default_value"] = deepcopy(metadata["default_value"])
    if "prefill" in metadata:
        normalized["prefill"] = deepcopy(metadata["prefill"])
    if "default_expr" in metadata:
        default_expr = metadata["default_expr"]
        if not _is_str_object_dict(default_expr):
            raise ValueError(f"{primitive_id}@1 default_expr must be ExprRef")
        value = resolve_expr(
            default_expr,
            f"{path_prefix}.default_expr",
            normalized,
        )
        if value is not None:
            normalized["default_value"] = value
    if "prefill_expr" in metadata:
        prefill_expr = metadata["prefill_expr"]
        if not _is_str_object_dict(prefill_expr):
            raise ValueError(f"{primitive_id}@1 prefill_expr must be ExprRef")
        value = resolve_expr(
            prefill_expr,
            f"{path_prefix}.prefill_expr",
            normalized,
        )
        if value is not None:
            normalized["prefill"] = value
    if "autofill_if" in metadata:
        autofill_expr = metadata["autofill_if"]
        if not _is_str_object_dict(autofill_expr):
            raise ValueError(f"{primitive_id}@1 autofill_if must be ExprRef")
        value = resolve_expr(
            autofill_expr,
            f"{path_prefix}.autofill_if",
            normalized,
        )
        if not isinstance(value, bool):
            raise ValueError(f"{primitive_id}@1 autofill_if must resolve to bool")
        normalized["autofill_if"] = value
    return normalized


def validate_submit_payload(
    primitive_id: str,
    primitive_version: int,
    payload: dict[str, object],
) -> dict[str, object]:
    if primitive_version != 1:
        raise ValueError("unsupported primitive version")
    if primitive_id == "ui.prompt_text":
        if set(payload.keys()) != {"value"}:
            raise ValueError("ui.prompt_text@1 payload must be {'value': <json>}")
        return {"value": payload.get("value")}
    if primitive_id == "ui.prompt_select":
        if set(payload.keys()) != {"selection"}:
            raise ValueError("ui.prompt_select@1 payload must be {'selection': <json>}")
        return {"selection": payload.get("selection")}
    if primitive_id == "ui.prompt_confirm":
        if set(payload.keys()) != {"confirmed"}:
            raise ValueError("ui.prompt_confirm@1 payload must be {'confirmed': <bool>}")
        confirmed = payload.get("confirmed")
        if not isinstance(confirmed, bool):
            raise ValueError("ui.prompt_confirm@1 confirmed must be bool")
        return {"confirmed": confirmed}
    raise ValueError("unknown ui primitive")


def execute_non_prompt(
    primitive_id: str,
    primitive_version: int,
    inputs: dict[str, object],
) -> dict[str, object]:
    if primitive_version != 1:
        raise ValueError("unsupported primitive version")
    if primitive_id == "ui.message":
        return {}
    raise ValueError("unknown non-prompt ui primitive")
