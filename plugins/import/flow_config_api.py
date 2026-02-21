"""FlowConfig API helpers for ImportWizardEngine.

Kept out of engine.py to avoid contributing to monolith growth.

ASCII-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from plugins.file_io.service.types import RootName

from .defaults import ensure_default_models
from .errors import FinalizeError
from .flow_config_patch import apply_patch_request
from .models import BASE_REQUIRED_STEP_IDS
from .storage import atomic_write_json, read_json

if TYPE_CHECKING:  # pragma: no cover
    from .engine import ImportWizardEngine


def normalize_flow_config(raw: Any) -> dict[str, Any]:
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


def merge_flow_config_overrides(
    base: dict[str, Any],
    overrides: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(overrides, dict):
        raise ValueError("flow_overrides must be an object")
    if "steps" not in overrides:
        return base
    merged = dict(base)
    steps = dict(cast(dict[str, Any], merged.get("steps") or {}))
    raw_steps = overrides.get("steps")
    if not isinstance(raw_steps, dict):
        raise ValueError("flow_overrides.steps must be an object")
    for step_id, cfg in raw_steps.items():
        if not isinstance(step_id, str) or not step_id:
            raise ValueError("flow_overrides.steps keys must be strings")
        if not isinstance(cfg, dict):
            raise ValueError("flow_overrides.steps.<step_id> must be an object")
        enabled = cfg.get("enabled")
        if enabled is None:
            continue
        if not isinstance(enabled, bool):
            raise ValueError("flow_overrides.steps.<step_id>.enabled must be bool")
        if enabled is False and step_id in BASE_REQUIRED_STEP_IDS:
            raise FinalizeError(f"required step may not be disabled: {step_id}")
        steps[step_id] = {"enabled": bool(enabled)}
    merged["steps"] = steps
    return merged


def get_flow_config(self: ImportWizardEngine) -> dict[str, Any]:
    """Return the current normalized FlowConfig JSON."""

    ensure_default_models(self._fs)
    flow_cfg = read_json(
        self._fs,
        RootName.WIZARDS,
        "import/config/flow_config.json",
    )
    return normalize_flow_config(flow_cfg)


def set_flow_config(self: ImportWizardEngine, flow_config_json: Any) -> dict[str, Any]:
    """Validate, normalize, persist, and return FlowConfig JSON."""

    patch_out = apply_patch_request(self, flow_config_json)
    if patch_out is not None:
        return patch_out

    validated = self.validate_flow_config(flow_config_json)
    if validated.get("ok") is not True:
        return validated

    ensure_default_models(self._fs)

    normalized = normalize_flow_config(flow_config_json)
    atomic_write_json(
        self._fs,
        RootName.WIZARDS,
        "import/config/flow_config.json",
        normalized,
    )
    return normalized


def reset_flow_config(self: ImportWizardEngine) -> dict[str, Any]:
    """Reset FlowConfig to DEFAULT_FLOW_CONFIG and return the normalized config."""

    from .defaults import DEFAULT_FLOW_CONFIG

    validated = self.validate_flow_config(DEFAULT_FLOW_CONFIG)
    if validated.get("ok") is not True:
        return validated

    ensure_default_models(self._fs)

    normalized = normalize_flow_config(DEFAULT_FLOW_CONFIG)
    atomic_write_json(
        self._fs,
        RootName.WIZARDS,
        "import/config/flow_config.json",
        normalized,
    )
    return normalized
