"""Field schema validation for import wizard wire contracts.

This module validates field definitions (10.4.3) before payload processing.

ASCII-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FieldSchemaValidationError(Exception):
    message: str
    path: str
    reason: str
    meta: dict[str, Any]

    def __str__(self) -> str:  # pragma: no cover
        return self.message


_BASELINE_TYPES = {
    "text",
    "toggle",
    "confirm",
    "select",
    "number",
    "multi_select_indexed",
    "table_edit",
}


def _ascii_only(*, value: str, path: str, meta: dict[str, Any]) -> None:
    try:
        value.encode("ascii")
    except UnicodeEncodeError as e:
        raise FieldSchemaValidationError(
            message="value must be ASCII-only",
            path=path,
            reason="non_ascii",
            meta=dict(meta),
        ) from e


def validate_step_fields(*, step_id: str, fields_any: Any) -> list[dict[str, Any]]:
    """Validate and return step field definitions.

    Baseline field types are defined in spec 10.4.3.

    Required invariants:
      - fields must be a list of objects
      - each field must include name (str) and type (str)
      - each field must include required (bool)
      - type-specific required properties are enforced where applicable
    """

    if not isinstance(fields_any, list):
        raise FieldSchemaValidationError(
            message="step schema fields must be a list",
            path="$.schema.fields",
            reason="invalid_type",
            meta={"step_id": step_id},
        )

    out: list[dict[str, Any]] = []
    for idx, fld in enumerate(fields_any):
        pfx = f"$.schema.fields[{idx}]"
        if not isinstance(fld, dict):
            raise FieldSchemaValidationError(
                message="field definition must be an object",
                path=pfx,
                reason="invalid_type",
                meta={"step_id": step_id},
            )

        name = fld.get("name")
        ftype = fld.get("type")
        if not isinstance(name, str) or not name:
            raise FieldSchemaValidationError(
                message="field.name must be a non-empty string",
                path=f"{pfx}.name",
                reason="missing_or_invalid",
                meta={"step_id": step_id},
            )
        _ascii_only(value=name, path=f"{pfx}.name", meta={"step_id": step_id})

        if not isinstance(ftype, str) or not ftype:
            raise FieldSchemaValidationError(
                message="field.type must be a non-empty string",
                path=f"{pfx}.type",
                reason="missing_or_invalid",
                meta={"step_id": step_id, "name": name},
            )
        if ftype not in _BASELINE_TYPES:
            raise FieldSchemaValidationError(
                message="unsupported field type",
                path=f"{pfx}.type",
                reason="unsupported_type",
                meta={"step_id": step_id, "name": name, "type": ftype},
            )

        required = fld.get("required")
        if required is None:
            raise FieldSchemaValidationError(
                message="field.required is required",
                path=f"{pfx}.required",
                reason="missing_required",
                meta={"step_id": step_id, "name": name, "type": ftype},
            )
        if not isinstance(required, bool):
            raise FieldSchemaValidationError(
                message="field.required must be bool",
                path=f"{pfx}.required",
                reason="invalid_type",
                meta={"step_id": step_id, "name": name, "type": ftype},
            )

        constraints = fld.get("constraints")
        if constraints is not None and not isinstance(constraints, dict):
            raise FieldSchemaValidationError(
                message="field.constraints must be an object",
                path=f"{pfx}.constraints",
                reason="invalid_type",
                meta={"step_id": step_id, "name": name, "type": ftype},
            )

        if ftype == "number":
            if constraints is None:
                raise FieldSchemaValidationError(
                    message="number.constraints is required",
                    path=f"{pfx}.constraints",
                    reason="missing_required",
                    meta={"step_id": step_id, "name": name},
                )
            mn = constraints.get("min")
            mx = constraints.get("max")
            if mn is not None and not isinstance(mn, int):
                raise FieldSchemaValidationError(
                    message="number.constraints.min must be int",
                    path=f"{pfx}.constraints.min",
                    reason="invalid_type",
                    meta={"step_id": step_id, "name": name},
                )
            if mx is not None and not isinstance(mx, int):
                raise FieldSchemaValidationError(
                    message="number.constraints.max must be int",
                    path=f"{pfx}.constraints.max",
                    reason="invalid_type",
                    meta={"step_id": step_id, "name": name},
                )

        if ftype == "multi_select_indexed":
            if "items" not in fld:
                raise FieldSchemaValidationError(
                    message="multi_select_indexed.items is required",
                    path=f"{pfx}.items",
                    reason="missing_required",
                    meta={"step_id": step_id, "name": name},
                )

            items = fld.get("items")
            if not isinstance(items, list):
                raise FieldSchemaValidationError(
                    message="multi_select_indexed.items must be a list",
                    path=f"{pfx}.items",
                    reason="invalid_type",
                    meta={"step_id": step_id, "name": name},
                )

            for j, it in enumerate(items):
                ipfx = f"{pfx}.items[{j}]"
                if not isinstance(it, dict):
                    raise FieldSchemaValidationError(
                        message="items[] entries must be objects",
                        path=ipfx,
                        reason="invalid_type",
                        meta={"step_id": step_id, "name": name},
                    )
                item_id = it.get("item_id")
                label = it.get("label")
                if not isinstance(item_id, str) or not item_id:
                    raise FieldSchemaValidationError(
                        message="items[].item_id must be a non-empty string",
                        path=f"{ipfx}.item_id",
                        reason="missing_or_invalid",
                        meta={"step_id": step_id, "name": name},
                    )
                _ascii_only(
                    value=item_id,
                    path=f"{ipfx}.item_id",
                    meta={"step_id": step_id, "name": name},
                )
                if not isinstance(label, str) or not label:
                    raise FieldSchemaValidationError(
                        message="items[].label must be a non-empty string",
                        path=f"{ipfx}.label",
                        reason="missing_or_invalid",
                        meta={"step_id": step_id, "name": name},
                    )
                _ascii_only(
                    value=label,
                    path=f"{ipfx}.label",
                    meta={"step_id": step_id, "name": name},
                )

        out.append(dict(fld))

    return out
