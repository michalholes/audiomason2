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
from .flow_config_validation import normalize_flow_config
from .models import BASE_REQUIRED_STEP_IDS
from .storage import atomic_write_json, read_json

if TYPE_CHECKING:  # pragma: no cover
    from .engine import ImportWizardEngine


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
