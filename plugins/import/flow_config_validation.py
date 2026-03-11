"""FlowConfig validation helpers for the import wizard.

This module is the single source of truth for FlowConfig bootstrap validation.

ASCII-only.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .errors import FinalizeError
from .field_schema_validation import FieldSchemaValidationError
from .models import BASE_REQUIRED_STEP_IDS

_ALLOWED_KEYS = {"version", "steps", "defaults"}
_ALLOWED_STEP_KEYS = {"enabled"}


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

    Defaults remain opaque editor payloads at this boundary. Projection metadata
    may help a UI render forms, but it must not become runtime or validation
    authority here. We therefore validate only the JSON object shape and preserve
    defaults payloads verbatim.
    """

    cfg = normalize_flow_config(raw)
    defaults_any = cfg.get("defaults") or {}
    if not isinstance(defaults_any, dict):
        return cfg

    validated_defaults: dict[str, Any] = {}
    for step_id, defaults_obj in sorted(defaults_any.items()):
        if not isinstance(defaults_obj, dict):
            validated_defaults[step_id] = deepcopy(defaults_obj)
            continue

        normalized_defaults: dict[str, Any] = {}
        for key, value in sorted(defaults_obj.items()):
            if not isinstance(key, str) or not key:
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
