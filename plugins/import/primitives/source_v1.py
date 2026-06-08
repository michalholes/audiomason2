"""Baseline v1 source primitives for import DSL runtime.

ASCII-only.
"""

from __future__ import annotations

import re
import unicodedata
from typing import TypeGuard, cast

_TRAILING_TAG_RE = re.compile(r"(?:\s*(?:\([^)]*\)|\[[^]]*\]))+\s*$")


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _ascii_fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return normalized.encode("ascii", "ignore").decode("ascii")


def _cleanup_whitespace(text: str) -> str:
    return " ".join(part for part in str(text).replace("_", " ").split() if part)


def _strip_trailing_tags(text: str) -> str:
    previous = str(text)
    while True:
        updated = _TRAILING_TAG_RE.sub("", previous).strip()
        if updated == previous:
            return updated
        previous = updated


def _normalize_label(value: object) -> str:
    text = _cleanup_whitespace(str(value or ""))
    text = _strip_trailing_tags(text)
    if "," in text:
        parts = [part.strip() for part in text.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            text = f"{parts[1]} {parts[0]}"
    text = _cleanup_whitespace(_ascii_fold(text))
    return text


def execute(
    primitive_id: str,
    primitive_version: int,
    inputs: dict[str, object],
    state: dict[str, object],
) -> dict[str, object]:
    del state
    if primitive_version != 1:
        raise ValueError("unsupported primitive version")

    if primitive_id == "source.normalize_label":
        value = inputs.get("value")
        return {"normalized": _normalize_label(value)}

    if primitive_id == "source.keys":
        items_any = inputs.get("items")
        items = _as_str_object_dict(items_any)
        return {"keys": [key for key in items]}

    raise ValueError(f"unknown primitive: {primitive_id}")


def _object_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {},
        "required": [],
        "description": "",
    }


REGISTRY_ENTRIES: list[dict[str, object]] = [
    {
        "primitive_id": "source.normalize_label",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": [],
    },
    {
        "primitive_id": "source.keys",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": [],
    },
]

__all__ = ["REGISTRY_ENTRIES", "execute"]
