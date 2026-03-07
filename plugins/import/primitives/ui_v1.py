"""Baseline v1 UI primitives for import DSL runtime.

ASCII-only.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any


def _object_schema(*, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {},
        "required": list(required or []),
        "description": "",
    }


REGISTRY_ENTRIES: list[dict[str, Any]] = [
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
PROMPT_RUNTIME_METADATA_KEYS: tuple[str, ...] = (
    "default_value",
    "prefill",
    "default_expr",
    "prefill_expr",
    "autofill_if",
)
PROMPT_METADATA_KEYS: tuple[str, ...] = (
    *PROMPT_RENDERER_METADATA_KEYS,
    *PROMPT_RUNTIME_METADATA_KEYS,
)
_EXPR_METADATA_KEYS: tuple[str, ...] = (
    "default_expr",
    "prefill_expr",
    "autofill_if",
)


def _is_expr_ref(value: Any) -> bool:
    return (
        isinstance(value, dict)
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
    inputs: dict[str, Any],
) -> dict[str, Any] | None:
    if not is_prompt_primitive(primitive_id, primitive_version):
        return None
    out: dict[str, Any] = {}
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
    metadata: dict[str, Any],
    *,
    resolve_expr: Callable[[dict[str, Any], str, dict[str, Any]], Any],
    path_prefix: str,
) -> dict[str, Any]:
    if not is_prompt_primitive(primitive_id, primitive_version):
        return {}

    normalized: dict[str, Any] = {}
    for key in PROMPT_RENDERER_METADATA_KEYS:
        if key in metadata:
            normalized[key] = deepcopy(metadata[key])
    if "default_value" in metadata:
        normalized["default_value"] = deepcopy(metadata["default_value"])
    if "prefill" in metadata:
        normalized["prefill"] = deepcopy(metadata["prefill"])
    if "default_expr" in metadata:
        normalized["default_value"] = resolve_expr(
            metadata["default_expr"],
            f"{path_prefix}.default_expr",
            normalized,
        )
    if "prefill_expr" in metadata:
        normalized["prefill"] = resolve_expr(
            metadata["prefill_expr"],
            f"{path_prefix}.prefill_expr",
            normalized,
        )
    if "autofill_if" in metadata:
        value = resolve_expr(
            metadata["autofill_if"],
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
    payload: dict[str, Any],
) -> dict[str, Any]:
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
    inputs: dict[str, Any],
) -> dict[str, Any]:
    if primitive_version != 1:
        raise ValueError("unsupported primitive version")
    if primitive_id == "ui.message":
        return {}
    raise ValueError("unknown non-prompt ui primitive")
