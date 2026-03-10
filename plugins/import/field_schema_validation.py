"""Field schema validation for import wizard wire contracts.

This module validates field definitions (10.4.3) before payload processing.

ASCII-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
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

_SETTINGS_FIELD_TYPES = {"string", "bool", "int", "number", "json"}


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


_JSON_PRIMITIVE_TYPES = (str, int, float, bool, type(None))


def _validate_choice_values(*, values_any: Any, path: str, meta: dict[str, Any]) -> list[Any]:
    if not isinstance(values_any, list):
        raise FieldSchemaValidationError(
            message="field choices must be a list",
            path=path,
            reason="invalid_type",
            meta=dict(meta),
        )
    out: list[Any] = []
    for index, value in enumerate(values_any):
        if not isinstance(value, _JSON_PRIMITIVE_TYPES):
            raise FieldSchemaValidationError(
                message="field choices must contain JSON primitives",
                path=f"{path}[{index}]",
                reason="invalid_type",
                meta=dict(meta),
            )
        out.append(value)
    return out


def validate_settings_schema_fields(*, step_id: str, fields_any: Any) -> list[dict[str, Any]]:
    if not isinstance(fields_any, list):
        raise FieldSchemaValidationError(
            message="settings_schema.fields must be a list",
            path="$.settings_schema.fields",
            reason="invalid_type",
            meta={"step_id": step_id},
        )

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idx, field_any in enumerate(fields_any):
        pfx = f"$.settings_schema.fields[{idx}]"
        if not isinstance(field_any, dict):
            raise FieldSchemaValidationError(
                message="settings field definition must be an object",
                path=pfx,
                reason="invalid_type",
                meta={"step_id": step_id},
            )

        key = field_any.get("key")
        type_name = field_any.get("type")
        required = field_any.get("required")
        if not isinstance(key, str) or not key:
            raise FieldSchemaValidationError(
                message="field.key must be a non-empty string",
                path=f"{pfx}.key",
                reason="missing_or_invalid",
                meta={"step_id": step_id},
            )
        _ascii_only(value=key, path=f"{pfx}.key", meta={"step_id": step_id})
        if key in seen:
            raise FieldSchemaValidationError(
                message="field.key must be unique",
                path=f"{pfx}.key",
                reason="duplicate_key",
                meta={"step_id": step_id, "key": key},
            )
        seen.add(key)

        if not isinstance(type_name, str) or not type_name:
            raise FieldSchemaValidationError(
                message="field.type must be a non-empty string",
                path=f"{pfx}.type",
                reason="missing_or_invalid",
                meta={"step_id": step_id, "key": key},
            )
        if type_name not in _SETTINGS_FIELD_TYPES:
            raise FieldSchemaValidationError(
                message="unsupported settings field type",
                path=f"{pfx}.type",
                reason="unsupported_type",
                meta={"step_id": step_id, "key": key, "type": type_name},
            )
        if not isinstance(required, bool):
            raise FieldSchemaValidationError(
                message="field.required must be bool",
                path=f"{pfx}.required",
                reason="invalid_type",
                meta={"step_id": step_id, "key": key, "type": type_name},
            )

        out_field = {"key": key, "type": type_name, "required": required}
        if "default" in field_any:
            out_field["default"] = field_any.get("default")

        for list_key in ("choices", "options"):
            if list_key in field_any:
                out_field[list_key] = _validate_choice_values(
                    values_any=field_any.get(list_key),
                    path=f"{pfx}.{list_key}",
                    meta={"step_id": step_id, "key": key, "type": type_name},
                )

        for num_key in ("min", "max", "step"):
            if num_key not in field_any:
                continue
            value = field_any.get(num_key)
            if type_name in {"int"}:
                valid = isinstance(value, int)
            else:
                valid = isinstance(value, (int, float)) and not isinstance(value, bool)
            if not valid:
                raise FieldSchemaValidationError(
                    message=f"field.{num_key} has invalid type",
                    path=f"{pfx}.{num_key}",
                    reason="invalid_type",
                    meta={"step_id": step_id, "key": key, "type": type_name},
                )
            out_field[num_key] = value

        if "multiline" in field_any:
            multiline = field_any.get("multiline")
            if not isinstance(multiline, bool):
                raise FieldSchemaValidationError(
                    message="field.multiline must be bool",
                    path=f"{pfx}.multiline",
                    reason="invalid_type",
                    meta={"step_id": step_id, "key": key, "type": type_name},
                )
            out_field["multiline"] = multiline

        if "format" in field_any:
            fmt = field_any.get("format")
            if not isinstance(fmt, str) or not fmt:
                raise FieldSchemaValidationError(
                    message="field.format must be a non-empty string",
                    path=f"{pfx}.format",
                    reason="missing_or_invalid",
                    meta={"step_id": step_id, "key": key, "type": type_name},
                )
            _ascii_only(
                value=fmt,
                path=f"{pfx}.format",
                meta={"step_id": step_id, "key": key, "type": type_name},
            )
            out_field["format"] = fmt

        out.append(out_field)

    return out


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
                display_label = it.get("display_label")
                if display_label is not None and (
                    not isinstance(display_label, str) or not display_label
                ):
                    raise FieldSchemaValidationError(
                        message="items[].display_label must be a non-empty string",
                        path=f"{ipfx}.display_label",
                        reason="missing_or_invalid",
                        meta={"step_id": step_id, "name": name},
                    )

        out.append(dict(fld))

    return out
