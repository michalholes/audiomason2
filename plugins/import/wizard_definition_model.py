"""WizardDefinition model for the import wizard.

This module defines the default workflow ordering as data (Python-defined),
bootstraps a runtime JSON artifact under the wizards root if missing, and
produces an effective step ordering for session creation.

No repo JSON is authoritative.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from plugins.file_io.service import FileService
from plugins.file_io.service.types import RootName

from .errors import FinalizeError
from .flow_runtime import CANONICAL_STEP_ORDER, OPTIONAL_STEP_IDS
from .storage import atomic_write_json_if_missing, read_json

WIZARD_DEFINITION_REL_PATH = "import/definitions/wizard_definition.json"

# The default workflow definition is Python-defined and is used only for
# bootstrap if the runtime artifact is missing.
DEFAULT_WIZARD_DEFINITION: dict[str, Any] = {
    "version": 1,
    "wizard_id": "import",
    "steps": [{"step_id": sid} for sid in CANONICAL_STEP_ORDER],
}

_MANDATORY_STEP_IDS: tuple[str, ...] = (
    "select_authors",
    "select_books",
    "plan_preview_batch",
    "conflict_policy",
    "final_summary_confirm",
    "processing",
)


def load_or_bootstrap_wizard_definition(fs: FileService) -> dict[str, Any]:
    """Load WizardDefinition JSON, bootstrapping it if missing.

    The file is a runtime artifact located under the wizards root.
    """
    atomic_write_json_if_missing(
        fs,
        RootName.WIZARDS,
        WIZARD_DEFINITION_REL_PATH,
        DEFAULT_WIZARD_DEFINITION,
    )
    wd = read_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH)
    validate_wizard_definition_structure(wd)
    return wd


def validate_wizard_definition_structure(wd: Any) -> None:
    """Validate basic structure and types."""
    if not isinstance(wd, dict):
        raise FinalizeError("wizard_definition must be a JSON object")

    wizard_id = wd.get("wizard_id")
    if wizard_id != "import":
        raise FinalizeError("wizard_definition wizard_id must be 'import'")

    steps_any = wd.get("steps")
    if not isinstance(steps_any, list) or not steps_any:
        raise FinalizeError("wizard_definition steps must be a non-empty list")

    seen: set[str] = set()
    for s in steps_any:
        if not isinstance(s, dict):
            raise FinalizeError("wizard_definition steps must be objects")
        sid = s.get("step_id")
        if not isinstance(sid, str) or not sid:
            raise FinalizeError("wizard_definition step_id must be a non-empty string")
        if sid in seen:
            raise FinalizeError("wizard_definition step_id must be unique")
        seen.add(sid)


def build_effective_workflow_snapshot(
    *,
    wizard_definition: dict[str, Any],
    flow_config: dict[str, Any],
) -> list[str]:
    """Return the effective ordered step_ids for a session.

    Applies flow_config optional-step enable/disable rules.
    """
    steps_any = wizard_definition.get("steps")
    if not isinstance(steps_any, list):
        raise FinalizeError("wizard_definition steps must be a list")

    ordered: list[str] = []
    for s in steps_any:
        sid = s.get("step_id") if isinstance(s, dict) else None
        if not isinstance(sid, str) or not sid:
            raise FinalizeError("wizard_definition contains invalid step_id")
        if sid in OPTIONAL_STEP_IDS and not _is_enabled(sid, flow_config):
            continue
        ordered.append(sid)

    enforce_mandatory_constraints(ordered)
    return ordered


def enforce_mandatory_constraints(step_order: list[str]) -> None:
    """Enforce mandatory constraints from specification section 10.3."""
    for sid in _MANDATORY_STEP_IDS:
        if sid not in step_order:
            raise FinalizeError(f"wizard_definition missing mandatory step_id: {sid}")

    # Ordering: select_authors < select_books < plan_preview_batch <
    # conflict_policy < final_summary_confirm < processing
    required_chain = [
        "select_authors",
        "select_books",
        "plan_preview_batch",
        "conflict_policy",
        "final_summary_confirm",
        "processing",
    ]
    idxs = [step_order.index(sid) for sid in required_chain]
    if idxs != sorted(idxs):
        raise FinalizeError("wizard_definition violates mandatory ordering constraints")

    # processing must be the only PHASE 2 step and the only terminal step.
    # Phase is derived: only 'processing' is PHASE 2.
    if step_order.count("processing") != 1:
        raise FinalizeError("wizard_definition must contain exactly one 'processing' step")
    if step_order[-1] != "processing":
        raise FinalizeError("wizard_definition processing must be the terminal step")


def _is_enabled(step_id: str, flow_config: dict[str, Any]) -> bool:
    steps_any = flow_config.get("steps") if isinstance(flow_config, dict) else None
    if not isinstance(steps_any, dict):
        return True
    cfg_any = steps_any.get(step_id)
    if not isinstance(cfg_any, dict):
        return True
    enabled = cfg_any.get("enabled")
    if enabled is None:
        return True
    return bool(enabled)
