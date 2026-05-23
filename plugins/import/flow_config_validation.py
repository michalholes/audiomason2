"""FlowConfig validation helpers for the import wizard.

This module is the single source of truth for FlowConfig bootstrap validation.

ASCII-only.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TypeGuard, cast

from .errors import FinalizeError
from .field_schema_validation import FieldSchemaValidationError
from .models import BASE_REQUIRED_STEP_IDS

_ALLOWED_KEYS = {"version", "steps", "defaults"}
_ALLOWED_STEP_KEYS = {"enabled"}


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def normalize_flow_config(raw: object) -> dict[str, object]:
    """Validate and normalize FlowConfig v1.

    FlowConfig is a user-overrides document. It must remain minimal and only
    contain recognized keys.
    """

    if not _is_str_object_dict(raw):
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
        steps_doc: dict[str, object] = {}
    elif _is_str_object_dict(steps_any):
        steps_doc = steps_any
    else:
        raise ValueError("flow_config.steps must be an object")

    steps: dict[str, object] = {}
    for step_id, cfg_any in steps_doc.items():
        if not step_id:
            raise ValueError("flow_config.steps keys must be non-empty strings")
        if not _is_str_object_dict(cfg_any):
            raise ValueError("flow_config.steps.<step_id> must be an object")
        unknown_cfg = sorted(set(cfg_any.keys()) - _ALLOWED_STEP_KEYS)
        if unknown_cfg:
            raise ValueError("flow_config step contains unknown key(s): " + ", ".join(unknown_cfg))
        enabled = cfg_any.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            raise ValueError("flow_config.steps.<step_id>.enabled must be bool")
        if enabled is False and step_id in BASE_REQUIRED_STEP_IDS:
            raise FinalizeError(f"required step may not be disabled: {step_id}")
        if enabled is None:
            continue
        steps[step_id] = {"enabled": bool(enabled)}

    defaults_any = raw.get("defaults", {})
    if defaults_any is None:
        defaults_doc: dict[str, object] = {}
    elif _is_str_object_dict(defaults_any):
        defaults_doc = defaults_any
    else:
        raise ValueError("flow_config.defaults must be an object")

    return {
        "version": 1,
        "steps": steps,
        "defaults": deepcopy(defaults_doc),
    }


def validate_flow_config_editor_boundary(raw: object) -> dict[str, object]:
    """Apply editor-only FlowConfig validation without redefining authority.

    Defaults remain opaque editor payloads at this boundary. Projection metadata
    may help a UI render forms, but it must not become runtime or validation
    authority here. We therefore validate only the JSON object shape and preserve
    defaults payloads verbatim.
    """

    cfg = normalize_flow_config(raw)
    defaults_any = cfg.get("defaults")
    if not _is_str_object_dict(defaults_any):
        return cfg

    validated_defaults: dict[str, object] = {}
    for step_id, defaults_obj in sorted(defaults_any.items()):
        if not _is_str_object_dict(defaults_obj):
            validated_defaults[step_id] = deepcopy(defaults_obj)
            continue

        normalized_defaults: dict[str, object] = {}
        for key, value in sorted(defaults_obj.items()):
            if not key:
                raise FieldSchemaValidationError(
                    message="flow_config defaults keys must be non-empty strings",
                    path=f"$.defaults.{step_id}",
                    reason="missing_or_invalid",
                    meta={"step_id": step_id},
                )
            normalized_defaults[key] = deepcopy(value)
        validated_defaults[step_id] = normalized_defaults

    cfg["defaults"] = validated_defaults
    return cfg
