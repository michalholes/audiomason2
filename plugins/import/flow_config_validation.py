"""FlowConfig validation helpers for the import wizard.

This module is the single source of truth for FlowConfig bootstrap validation.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from .errors import FinalizeError
from .models import BASE_REQUIRED_STEP_IDS


def normalize_flow_config(raw: Any) -> dict[str, Any]:
    """Validate and normalize FlowConfig v1.

    FlowConfig is a user-overrides document. It must remain minimal and only
    contain recognized keys.
    """

    if not isinstance(raw, dict):
        raise ValueError("flow_config must be an object")

    allowed_keys = {"version", "steps", "defaults", "ui"}
    unknown = sorted(set(raw.keys()) - allowed_keys)
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
        enabled = cfg.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            raise ValueError("flow_config.steps.<step_id>.enabled must be bool")
        if enabled is False and step_id in BASE_REQUIRED_STEP_IDS:
            raise FinalizeError(f"required step may not be disabled: {step_id}")
        if enabled is None:
            continue
        steps[step_id] = {"enabled": bool(enabled)}

    defaults_any = raw.get("defaults", {})
    ui_any = raw.get("ui", {})
    if defaults_any is None:
        defaults_any = {}
    if ui_any is None:
        ui_any = {}
    if not isinstance(defaults_any, dict):
        raise ValueError("flow_config.defaults must be an object")
    if not isinstance(ui_any, dict):
        raise ValueError("flow_config.ui must be an object")

    ui: dict[str, Any] = dict(ui_any)
    verbosity_any = ui_any.get("verbosity")
    if verbosity_any is not None:
        if not isinstance(verbosity_any, str) or not verbosity_any.strip():
            raise ValueError("flow_config.ui.verbosity must be a non-empty string")
        verbosity = verbosity_any.strip().lower()
        try:
            verbosity.encode("ascii")
        except UnicodeEncodeError as e:
            raise ValueError("flow_config.ui.verbosity must be ASCII-only") from e
        ui["verbosity"] = verbosity

    return {
        "version": 1,
        "steps": steps,
        "defaults": defaults_any,
        "ui": ui,
    }
