"""Submit-step implementation for the import wizard engine.

Split out of engine.py to satisfy monolith constraints.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from plugins.file_io.service.types import RootName

from .dsl.interpreter_v3 import submit_current_step
from .engine_actions_v3 import is_v3_effective_model
from .engine_conflicts import (
    apply_conflict_policy,
    apply_conflict_resolve,
    persist_conflict_resolution,
)
from .engine_util import (
    _derive_selection_items,
    _emit_required,
    _exception_envelope,
    _iso_utc_now,
    _parse_selection_expr,
    sync_session_cursor,
)
from .errors import StepSubmissionError, ascii_message, invariant_violation
from .flow_runtime import CONDITIONAL_STEP_IDS
from .phase1_source_intake import build_phase1_projection, phase1_session_authority_applies
from .storage import read_json


def _selection_ids_from_value(*, ordered_ids: list[str], selection: Any) -> list[str]:
    if not ordered_ids:
        return []

    ordered_set = set(ordered_ids)
    if isinstance(selection, list):
        if all(isinstance(item, str) for item in selection):
            requested = [str(item) for item in selection]
            if all(item in ordered_set for item in requested):
                requested_set = set(requested)
                return [item_id for item_id in ordered_ids if item_id in requested_set]
            return []
        if all(isinstance(item, int) and not isinstance(item, bool) for item in selection):
            requested_indices = {int(item) for item in selection if int(item) > 0}
            return [
                item_id
                for index, item_id in enumerate(ordered_ids, start=1)
                if index in requested_indices
            ]
        return []

    if isinstance(selection, int) and not isinstance(selection, bool):
        selection = str(selection)

    if not isinstance(selection, str):
        return []

    try:
        requested_indices = set(_parse_selection_expr(selection, max_index=len(ordered_ids)))
    except ValueError:
        return []

    return [
        item_id for index, item_id in enumerate(ordered_ids, start=1) if index in requested_indices
    ]


def _derive_v3_selected_ids(
    *,
    engine: Any,
    session_id: str,
    step_id: str,
    selection: Any,
) -> list[str]:
    session_dir = f"import/sessions/{session_id}"
    discovery_any = read_json(engine._fs, RootName.WIZARDS, f"{session_dir}/discovery.json")
    if not isinstance(discovery_any, list) or not all(
        isinstance(item, dict) for item in discovery_any
    ):
        return []

    discovery = [dict(item) for item in discovery_any]
    authors_items, books_items = _derive_selection_items(discovery)
    items = authors_items if step_id == "select_authors" else books_items
    ordered_ids = [
        str(item.get("item_id")) for item in items if isinstance(item.get("item_id"), str)
    ]
    return _selection_ids_from_value(ordered_ids=ordered_ids, selection=selection)


def _validate_v3_selection_payload(
    *,
    engine: Any,
    session_id: str,
    step_id: str,
    payload: dict[str, Any],
) -> None:
    if step_id not in {"select_authors", "select_books"}:
        return
    if "selection" not in payload:
        return

    selection = payload.get("selection")
    if selection in (None, "", []):
        raise StepSubmissionError("selection is required")

    selected_ids = _derive_v3_selected_ids(
        engine=engine,
        session_id=session_id,
        step_id=step_id,
        selection=selection,
    )
    if selected_ids:
        return
    raise StepSubmissionError("selection out of range")


def _sync_v3_legacy_state(*, engine: Any, session_id: str, state: dict[str, Any]) -> dict[str, Any]:
    answers = dict(state.get("answers") or {})
    inputs = dict(state.get("inputs") or {})

    for mirrored_step_id in (
        "select_authors",
        "select_books",
        "conflict_policy",
        "final_summary_confirm",
    ):
        answer_any = answers.get(mirrored_step_id)
        if isinstance(answer_any, dict):
            inputs[mirrored_step_id] = dict(answer_any)

    state["inputs"] = inputs

    authors_any = inputs.get("select_authors")
    if isinstance(authors_any, dict):
        state["selected_author_ids"] = _derive_v3_selected_ids(
            engine=engine,
            session_id=session_id,
            step_id="select_authors",
            selection=authors_any.get("selection_expr"),
        )

    books_any = inputs.get("select_books")
    if isinstance(books_any, dict):
        state["selected_book_ids"] = _derive_v3_selected_ids(
            engine=engine,
            session_id=session_id,
            step_id="select_books",
            selection=books_any.get("selection_expr"),
        )

    return state


def _needs_v3_plan_refresh(state: dict[str, Any]) -> bool:
    computed_any = state.get("computed")
    if isinstance(computed_any, dict) and "plan_summary" in computed_any:
        return False

    trace_any = state.get("trace")
    if not isinstance(trace_any, list):
        return False

    return any(
        isinstance(entry, dict) and entry.get("step_id") == "plan_preview_batch"
        for entry in trace_any
    )


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
        if is_v3_effective_model(effective_model):
            _validate_v3_selection_payload(
                engine=engine,
                session_id=session_id,
                step_id=step_id,
                payload=payload,
            )
            next_state = submit_current_step(
                effective_model=effective_model,
                state=state,
                session_id=session_id,
                step_id=step_id,
                payload=payload,
            )
            next_state = _sync_v3_legacy_state(
                engine=engine,
                session_id=session_id,
                state=next_state,
            )
            session_dir = f"import/sessions/{session_id}"
            discovery_any = read_json(engine._fs, RootName.WIZARDS, f"{session_dir}/discovery.json")
            if (
                phase1_session_authority_applies(effective_model=effective_model)
                and isinstance(discovery_any, list)
                and all(isinstance(item, dict) for item in discovery_any)
            ):
                next_state.setdefault("vars", {})["phase1"] = build_phase1_projection(
                    discovery=discovery_any,
                    state=next_state,
                )
            next_state["updated_at"] = _iso_utc_now()
            engine._persist_state(session_id, next_state)
            if _needs_v3_plan_refresh(next_state):
                engine.compute_plan(session_id)
                next_state = engine._load_state(session_id)
            engine._append_decision(
                session_id,
                step_id=step_id,
                payload=dict(payload),
                result="accepted",
                error=None,
            )
            return next_state
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
        sync_session_cursor(state, step_id=str(state.get("current_step_id") or ""))

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
