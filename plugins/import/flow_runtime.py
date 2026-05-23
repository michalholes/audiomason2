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

from typing import TypeGuard, cast

from .errors import FinalizeError
from .models import CatalogModel

FLOW_ID = "import_v1"

# Spec 10.3.1 canonical step_ids (including the conditional and PHASE 2 terminal).
# This list is NOT a runtime authority. It exists only as a stable default for
# bootstrapping DEFAULT_WIZARD_DEFINITION.
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
    "skip_processed_books",
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
    "skip_processed_books",
    "parallelism",
}

# Mandatory steps that MUST NOT be removed or disabled.
# Spec 10.3/10.6: these are fixed invariants, independent of the canonical order.
MANDATORY_STEP_IDS: set[str] = {
    "select_authors",
    "select_books",
    "plan_preview_batch",
    "conflict_policy",
    "final_summary_confirm",
    "processing",
}


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_enabled(step_id: str, flow_cfg: dict[str, object]) -> bool:
    steps_any = flow_cfg.get("steps", {})
    if not _is_str_object_dict(steps_any):
        return True
    cfg = steps_any.get(step_id)
    if not _is_str_object_dict(cfg):
        return True
    enabled = cfg.get("enabled")
    if enabled is None:
        return True
    return bool(enabled)


def build_flow_model(
    *,
    catalog: CatalogModel,
    flow_config: dict[str, object],
    step_order: list[str],
) -> dict[str, object]:
    """Build the runtime FlowModel dict (spec 10.4.5).

    Raises FinalizeError for invariant violations (mapped to INVARIANT_VIOLATION).
    """

    step_defs: dict[str, dict[str, object]] = {}
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

    steps: list[dict[str, object]] = []

    def add_step(step_id: str) -> None:
        if step_id in OPTIONAL_STEP_IDS and not _is_enabled(step_id, flow_config):
            return
        s = step_defs[step_id]
        phase = 2 if step_id == "processing" else 1
        required = step_id in MANDATORY_STEP_IDS
        fields_any = s.get("fields")
        fields = [field for field in fields_any] if _is_object_list(fields_any) else []
        eff_step: dict[str, object] = {
            "step_id": step_id,
            "title": str(s.get("title") or step_id),
            "phase": phase,
            "required": required,
            "fields": fields,
        }

        execution_any = s.get("execution")
        if execution_any is not None:
            eff_step["execution"] = execution_any

        job_req_any = s.get("job_request")
        if job_req_any is not None:
            eff_step["job_request"] = job_req_any

        steps.append(eff_step)

    for sid in step_order:
        add_step(sid)

    return {"flow_id": FLOW_ID, "steps": steps}
