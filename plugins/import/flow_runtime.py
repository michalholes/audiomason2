"""Runtime FlowModel builder for the import wizard.

Generates the UI-facing FlowModel (spec 10.4.5) from:
- CatalogModel (step schemas)
- FlowConfig (optional-step enable/disable)

The returned dict is suitable for:
- GET /import/ui/flow
- sessions/<id>/effective_model.json snapshot (spec 10.9)

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from .errors import FinalizeError
from .models import CatalogModel

FLOW_ID = "import_v1"

# Spec 10.3.1 canonical step_ids (including the conditional and PHASE 2 terminal).
CANONICAL_STEP_ORDER: list[str] = [
    "select_authors",
    "select_books",
    "plan_preview_batch",
    "effective_author_title",
    "filename_policy",
    "covers_policy",
    "id3_policy",
    "audio_processing",
    "publish_policy",
    "delete_source_policy",
    "conflict_policy",
    "parallelism",
    "final_summary_confirm",
    "resolve_conflicts_batch",
    "processing",
]

# Conditional step (spec 10.3.4).
CONDITIONAL_STEP_IDS: set[str] = {"resolve_conflicts_batch"}

# Optional steps that may be disabled by FlowConfig (spec 10.3.2).
OPTIONAL_STEP_IDS: set[str] = {
    "filename_policy",
    "covers_policy",
    "id3_policy",
    "audio_processing",
    "publish_policy",
    "delete_source_policy",
    "parallelism",
}

# Mandatory steps that MUST NOT be removed or disabled (spec 10.6).
MANDATORY_STEP_IDS: set[str] = set(CANONICAL_STEP_ORDER) - OPTIONAL_STEP_IDS
MANDATORY_STEP_IDS |= CONDITIONAL_STEP_IDS


def _is_enabled(step_id: str, flow_cfg: dict[str, Any]) -> bool:
    steps_any = flow_cfg.get("steps", {})
    if not isinstance(steps_any, dict):
        return True
    cfg = steps_any.get(step_id)
    if not isinstance(cfg, dict):
        return True
    enabled = cfg.get("enabled")
    if enabled is None:
        return True
    return bool(enabled)


def build_flow_model(
    *,
    catalog: CatalogModel,
    flow_config: dict[str, Any],
    step_order: list[str],
) -> dict[str, Any]:
    """Build the runtime FlowModel dict (spec 10.4.5).

    Raises FinalizeError for invariant violations (mapped to INVARIANT_VIOLATION).
    """

    step_defs: dict[str, dict[str, Any]] = {}
    for s in catalog.steps:
        sid = s.get("step_id")
        if isinstance(sid, str) and sid:
            step_defs[sid] = dict(s)

    missing = sorted(set(step_order) - set(step_defs.keys()))
    if missing:
        raise FinalizeError("catalog missing required step definitions")

    # Engine Guards (spec 10.6): mandatory steps must not be disabled.
    for sid in sorted(MANDATORY_STEP_IDS):
        if not _is_enabled(sid, flow_config):
            raise FinalizeError(f"required step may not be disabled: {sid}")

    steps: list[dict[str, Any]] = []

    def add_step(step_id: str) -> None:
        if step_id in OPTIONAL_STEP_IDS and not _is_enabled(step_id, flow_config):
            return
        s = step_defs[step_id]
        phase = 2 if step_id == "processing" else 1
        required = step_id in MANDATORY_STEP_IDS
        steps.append(
            {
                "step_id": step_id,
                "title": str(s.get("title") or step_id),
                "phase": phase,
                "required": required,
                "fields": list(s.get("fields") or []),
            }
        )

    for sid in step_order:
        add_step(sid)

    return {"flow_id": FLOW_ID, "steps": steps}
