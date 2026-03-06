"""Baseline v1 UI primitives for import DSL runtime.

ASCII-only.
"""

from __future__ import annotations

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
    {
        "primitive_id": "select_authors",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(required=["selection"]),
        "determinism_notes": "legacy_compat",
        "allowed_errors": ["VALIDATION_ERROR"],
    },
]


PROMPT_IDS: set[str] = {
    "ui.prompt_text",
    "ui.prompt_select",
    "ui.prompt_confirm",
    "select_authors",
}


OUTPUT_KEYS: dict[str, str] = {
    "ui.prompt_text": "value",
    "ui.prompt_select": "selection",
    "ui.prompt_confirm": "confirmed",
    "select_authors": "selection",
}


def is_prompt_primitive(primitive_id: str, primitive_version: int) -> bool:
    return primitive_version == 1 and primitive_id in PROMPT_IDS


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
    if primitive_id in {"ui.prompt_select", "select_authors"}:
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
