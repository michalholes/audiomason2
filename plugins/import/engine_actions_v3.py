"""Backend helpers for WizardDefinition v3 engine dispatch.

ASCII-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .dsl.flowmodel_v3 import FLOWMODEL_KIND, build_flow_model_v3
from .dsl.interpreter_v3 import run_automatic_steps
from .engine_util import iso_utc_now, sync_session_cursor
from .errors import StepSubmissionError, invariant_violation

if TYPE_CHECKING:
    from .engine import ImportWizardEngine


def build_runtime_flow_model(*, wizard_definition: dict[str, object]) -> dict[str, object]:
    return build_flow_model_v3(wizard_definition=wizard_definition)


def is_v3_effective_model(effective_model: dict[str, object]) -> bool:
    return str(effective_model.get("flowmodel_kind") or "") == FLOWMODEL_KIND


def initialize_state(
    *,
    state: dict[str, object],
    effective_model: dict[str, object],
    session_id: str,
) -> dict[str, object]:
    entry_step_id = str(effective_model.get("entry_step_id") or "")
    state["current_step_id"] = entry_step_id
    sync_session_cursor(state, step_id=entry_step_id)
    return run_automatic_steps(effective_model=effective_model, state=state, session_id=session_id)


def apply_action_v3(
    *, engine: ImportWizardEngine, session_id: str, action: str
) -> dict[str, object]:
    state = engine.load_state(session_id)
    effective_model = engine.load_effective_model(session_id)
    if not is_v3_effective_model(effective_model):
        raise StepSubmissionError("session is not v3")
    if action == "cancel":
        state["status"] = "aborted"
        state["updated_at"] = iso_utc_now()
        engine.persist_state(session_id, state)
        return state
    if state.get("status") != "in_progress":
        return invariant_violation(
            message="session is not in progress",
            path="$.status",
            reason="status_not_in_progress",
            meta={},
        )
    return run_automatic_steps(effective_model=effective_model, state=state, session_id=session_id)


__all__ = [
    "apply_action_v3",
    "build_runtime_flow_model",
    "initialize_state",
    "is_v3_effective_model",
]
