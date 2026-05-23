"""FlowConfig API helpers for ImportWizardEngine.

Kept out of engine.py to avoid contributing to monolith growth.

ASCII-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeGuard, cast

from plugins.file_io.service.types import RootName

from .errors import FinalizeError
from .flow_config_defaults import DEFAULT_FLOW_CONFIG, ensure_flow_config_exists
from .flow_config_patch import apply_patch_request
from .flow_config_validation import normalize_flow_config
from .models import BASE_REQUIRED_STEP_IDS
from .storage import atomic_write_json, read_json

if TYPE_CHECKING:  # pragma: no cover
    from .engine import ImportWizardEngine


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def merge_flow_config_overrides(
    base: dict[str, object],
    overrides: dict[str, object],
) -> dict[str, object]:
    if "steps" not in overrides:
        return base
    merged = dict(base)
    steps_any = merged.get("steps")
    steps: dict[str, object] = dict(steps_any) if _is_str_object_dict(steps_any) else {}
    raw_steps_any = overrides.get("steps")
    if not _is_str_object_dict(raw_steps_any):
        raise ValueError("flow_overrides.steps must be an object")
    for step_id, cfg_any in raw_steps_any.items():
        cfg = cfg_any if _is_str_object_dict(cfg_any) else None
        if not step_id:
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


def get_flow_config(self: ImportWizardEngine) -> dict[str, object]:
    """Return the current normalized FlowConfig JSON."""

    fs = self.get_file_service()
    ensure_flow_config_exists(fs)
    flow_cfg = read_json(
        fs,
        RootName.WIZARDS,
        "import/config/flow_config.json",
    )
    return normalize_flow_config(flow_cfg)


def set_flow_config(self: ImportWizardEngine, flow_config_json: object) -> dict[str, object]:
    """Validate, normalize, persist, and return FlowConfig JSON."""

    patch_out = apply_patch_request(self, flow_config_json)
    if patch_out is not None:
        return patch_out

    validated = self.validate_flow_config(flow_config_json)
    if validated.get("ok") is not True:
        return validated

    fs = self.get_file_service()
    ensure_flow_config_exists(fs)

    normalized = normalize_flow_config(flow_config_json)
    atomic_write_json(
        fs,
        RootName.WIZARDS,
        "import/config/flow_config.json",
        normalized,
    )
    return normalized


def reset_flow_config(self: ImportWizardEngine) -> dict[str, object]:
    """Reset FlowConfig to DEFAULT_FLOW_CONFIG and return the normalized config."""

    validated = self.validate_flow_config(DEFAULT_FLOW_CONFIG)
    if validated.get("ok") is not True:
        return validated

    fs = self.get_file_service()
    ensure_flow_config_exists(fs)

    normalized = normalize_flow_config(DEFAULT_FLOW_CONFIG)
    atomic_write_json(
        fs,
        RootName.WIZARDS,
        "import/config/flow_config.json",
        normalized,
    )
    return normalized
