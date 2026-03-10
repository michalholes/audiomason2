"""FlowConfig validation helpers for the import wizard.

This module is the single source of truth for FlowConfig bootstrap validation.

ASCII-only.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .errors import FinalizeError
from .field_schema_validation import FieldSchemaValidationError, validate_settings_schema_fields
from .models import BASE_REQUIRED_STEP_IDS

_ALLOWED_KEYS = {"version", "steps", "defaults"}
_ALLOWED_STEP_KEYS = {"enabled"}


def _step_details_for_editor(step_id: str) -> dict[str, Any] | None:
    from .step_catalog import get_step_details

    details = get_step_details(step_id)
    if isinstance(details, dict):
        return details
    return None


def _type_matches(type_name: str, value: Any) -> bool:
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "bool":
        return isinstance(value, bool)
    if type_name == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return type_name == "json"


def _validate_default_value(*, step_id: str, field: dict[str, Any], value: Any, path: str) -> Any:
    field_key = str(field.get("key") or "")
    type_name = str(field.get("type") or "")
    if not _type_matches(type_name, value):
        raise FieldSchemaValidationError(
            message="flow_config default has invalid type",
            path=path,
            reason="invalid_type",
            meta={"step_id": step_id, "key": field_key, "type": type_name},
        )

    choices = field.get("options")
    if not isinstance(choices, list):
        choices = field.get("choices")
    if isinstance(choices, list) and choices and value not in choices:
        raise FieldSchemaValidationError(
            message="flow_config default must match allowed choices",
            path=path,
            reason="invalid_enum",
            meta={"step_id": step_id, "key": field_key, "allowed": choices},
        )

    if type_name in {"int", "number"}:
        min_value = field.get("min")
        max_value = field.get("max")
        if isinstance(min_value, (int, float)) and value < min_value:
            raise FieldSchemaValidationError(
                message="flow_config default is below minimum",
                path=path,
                reason="value_too_small",
                meta={"step_id": step_id, "key": field_key, "min": min_value},
            )
        if isinstance(max_value, (int, float)) and value > max_value:
            raise FieldSchemaValidationError(
                message="flow_config default exceeds maximum",
                path=path,
                reason="value_too_large",
                meta={"step_id": step_id, "key": field_key, "max": max_value},
            )

    return deepcopy(value)


def normalize_flow_config(raw: Any) -> dict[str, Any]:
    """Validate and normalize FlowConfig v1.

    FlowConfig is a user-overrides document. It must remain minimal and only
    contain recognized keys.
    """

    if not isinstance(raw, dict):
        raise ValueError("flow_config must be an object")

    if "ui" in raw:
        raise ValueError("flow_config prohibits key: ui")

    unknown = sorted(set(raw.keys()) - _ALLOWED_KEYS)
    if unknown:
        raise ValueError("flow_config contains unknown key(s): " + ", ".join(unknown))

    version = raw.get("version")
    if version != 1:
        raise ValueError("flow_config.version must be 1")

    steps_any = raw.get("steps", {})
    if steps_any is None:
        steps_any = {}
    if not isinstance(steps_any, dict):
        raise ValueError("flow_config.steps must be an object")

    steps: dict[str, Any] = {}
    for step_id, cfg in steps_any.items():
        if not isinstance(step_id, str) or not step_id:
            raise ValueError("flow_config.steps keys must be non-empty strings")
        if not isinstance(cfg, dict):
            raise ValueError("flow_config.steps.<step_id> must be an object")
        unknown_cfg = sorted(set(cfg.keys()) - _ALLOWED_STEP_KEYS)
        if unknown_cfg:
            raise ValueError("flow_config step contains unknown key(s): " + ", ".join(unknown_cfg))
        enabled = cfg.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            raise ValueError("flow_config.steps.<step_id>.enabled must be bool")
        if enabled is False and step_id in BASE_REQUIRED_STEP_IDS:
            raise FinalizeError(f"required step may not be disabled: {step_id}")
        if enabled is None:
            continue
        steps[step_id] = {"enabled": bool(enabled)}

    defaults_any = raw.get("defaults", {})
    if defaults_any is None:
        defaults_any = {}
    if not isinstance(defaults_any, dict):
        raise ValueError("flow_config.defaults must be an object")

    return {
        "version": 1,
        "steps": steps,
        "defaults": deepcopy(defaults_any),
    }


def validate_flow_config_editor_boundary(raw: Any) -> dict[str, Any]:
    """Apply editor-only FlowConfig validation without redefining authority.

    Legacy defaults keys remain allowed. When a defaults entry targets a known
    step with a declared settings schema, its field names and values must be
    runtime-meaningful.
    """

    cfg = normalize_flow_config(raw)
    defaults_any = cfg.get("defaults") or {}
    if not isinstance(defaults_any, dict):
        return cfg

    validated_defaults: dict[str, Any] = {}
    for step_id, defaults_obj in sorted(defaults_any.items()):
        details = _step_details_for_editor(step_id)
        if details is None or not isinstance(defaults_obj, dict):
            validated_defaults[step_id] = deepcopy(defaults_obj)
            continue

        schema = details.get("settings_schema")
        fields = validate_settings_schema_fields(
            step_id=step_id,
            fields_any=(schema or {}).get("fields") if isinstance(schema, dict) else [],
        )
        field_map = {str(field.get("key")): field for field in fields}
        normalized_defaults: dict[str, Any] = {}
        for key, value in sorted(defaults_obj.items()):
            if not isinstance(key, str) or not key:
                raise FieldSchemaValidationError(
                    message="flow_config defaults keys must be non-empty strings",
                    path=f"$.defaults.{step_id}",
                    reason="missing_or_invalid",
                    meta={"step_id": step_id},
                )
            field = field_map.get(key)
            if field is None:
                raise FieldSchemaValidationError(
                    message="flow_config default key is not runtime-meaningful",
                    path=f"$.defaults.{step_id}.{key}",
                    reason="unknown_field",
                    meta={"step_id": step_id, "allowed": sorted(field_map.keys())},
                )
            normalized_defaults[key] = _validate_default_value(
                step_id=step_id,
                field=field,
                value=value,
                path=f"$.defaults.{step_id}.{key}",
            )
        validated_defaults[step_id] = normalized_defaults

    cfg["defaults"] = validated_defaults
    return cfg
