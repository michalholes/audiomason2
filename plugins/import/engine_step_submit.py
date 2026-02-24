"""Submit-step implementation for the import wizard engine.

Split out of engine.py to satisfy monolith constraints.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from .engine_conflicts import (
    apply_conflict_policy,
    apply_conflict_resolve,
    persist_conflict_resolution,
)
from .engine_util import (
    _emit_required,
    _exception_envelope,
    _iso_utc_now,
)
from .errors import StepSubmissionError, ascii_message, invariant_violation
from .flow_runtime import CONDITIONAL_STEP_IDS


def submit_step_impl(
    *,
    engine: Any,
    session_id: str,
    step_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        state = engine._load_state(session_id)
        if int(state.get("phase") or 1) == 2:
            return invariant_violation(
                message="session is locked (phase 2)",
                path="$.phase",
                reason="phase_locked",
                meta={},
            )
        if state.get("status") != "in_progress":
            raise StepSubmissionError("session is not in progress")

        _emit_required(
            "step.submit",
            "step.submit",
            {
                "session_id": session_id,
                "step_id": step_id,
                "model_fingerprint": state.get("model_fingerprint"),
                "discovery_fingerprint": state.get("derived", {}).get("discovery_fingerprint"),
                "effective_config_fingerprint": state.get("derived", {}).get(
                    "effective_config_fingerprint"
                ),
            },
        )

        if not isinstance(payload, dict):
            raise StepSubmissionError("payload must be an object")

        effective_model = engine._load_effective_model(session_id)
        steps_any = effective_model.get("steps")
        if not isinstance(steps_any, list):
            raise StepSubmissionError("effective model missing steps")
        steps = [s for s in steps_any if isinstance(s, dict)]
        flow_cfg_norm = engine._load_effective_flow_config(session_id)

        step_ids = {str(s.get("step_id")) for s in steps if isinstance(s.get("step_id"), str)}
        if step_id not in step_ids and step_id not in CONDITIONAL_STEP_IDS:
            raise StepSubmissionError("unknown step_id")

        current = str(state.get("current_step_id") or "select_authors")
        if step_id != current:
            raise StepSubmissionError("step_id must match current_step_id")

        schema = None
        for step in steps:
            if step.get("step_id") == step_id:
                schema = step
                break
        if schema is None:
            raise StepSubmissionError("unknown step_id")

        if step_id in {"plan_preview_batch", "processing"}:
            raise StepSubmissionError("computed-only step cannot be submitted")

        normalized_payload = engine._validate_and_canonicalize_payload(
            step_id=step_id,
            schema=schema,
            payload=payload,
            state=state,
        )

        if step_id == "conflict_policy":
            apply_conflict_policy(state=state, payload=normalized_payload)
        if step_id == "resolve_conflicts_batch":
            apply_conflict_resolve(state=state, payload=normalized_payload)
            persist_conflict_resolution(
                engine=engine,
                session_id=session_id,
                state=state,
                payload=normalized_payload,
            )

        answers = dict(state.get("answers") or {})
        answers[step_id] = normalized_payload
        state["answers"] = answers

        # Backward compatibility: maintain legacy inputs mirror.
        inputs = dict(state.get("inputs") or {})
        inputs[step_id] = normalized_payload
        state["inputs"] = inputs

        if step_id == "select_authors":
            sel = normalized_payload.get("selection")
            if isinstance(sel, list) and all(isinstance(x, str) for x in sel):
                state["selected_author_ids"] = list(sel)

        if step_id == "select_books":
            sel = normalized_payload.get("selection")
            if isinstance(sel, list) and all(isinstance(x, str) for x in sel):
                state["selected_book_ids"] = list(sel)

        if step_id == "effective_author_title":
            state["effective_author_title"] = dict(normalized_payload)

        completed = list(state.get("completed_step_ids") or [])
        if step_id not in completed:
            completed.append(step_id)
        state["completed_step_ids"] = completed

        next_step = engine._next_step_after_submit(
            step_id=step_id,
            state=state,
            flow_cfg_norm=flow_cfg_norm,
        )

        state["current_step_id"] = engine._auto_advance_computed_steps(
            session_id=session_id,
            state=state,
            next_step_id=next_step,
            flow_cfg_norm=flow_cfg_norm,
        )

        state["updated_at"] = _iso_utc_now()
        engine._append_decision(
            session_id,
            step_id=step_id,
            payload=normalized_payload,
            result="accepted",
            error=None,
        )
        engine._persist_state(session_id, state)
        return state
    except Exception as e:
        engine._append_decision(
            session_id,
            step_id=step_id,
            payload=payload if isinstance(payload, dict) else {"_invalid_payload": True},
            result="rejected",
            error={
                "type": e.__class__.__name__,
                "message": ascii_message(str(e) or e.__class__.__name__),
            },
        )
        return _exception_envelope(e)
