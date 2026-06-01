"""Submit-step implementation for the import wizard engine.

Split out of engine.py to satisfy monolith constraints.

ASCII-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeGuard, cast

from plugins.file_io.service.types import RootName

from .dsl.interpreter_v3 import run_automatic_steps, submit_current_step
from .engine_actions_v3 import is_v3_effective_model
from .engine_conflicts import (
    apply_conflict_policy,
    apply_conflict_resolve,
    persist_conflict_resolution,
)
from .engine_util import (
    derive_selection_items,
    emit_required_event,
    exception_envelope,
    iso_utc_now,
    parse_selection_expr,
    sync_session_cursor,
)
from .errors import StepSubmissionError, ascii_message, invariant_violation
from .flow_runtime import CONDITIONAL_STEP_IDS
from .phase1_source_intake import build_phase1_projection, phase1_session_authority_applies
from .storage import read_json

if TYPE_CHECKING:
    from .engine import ImportWizardEngine


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _selection_ids_from_value(*, ordered_ids: list[str], selection: object) -> list[str]:
    if not ordered_ids:
        return []

    ordered_set = set(ordered_ids)
    if _is_object_list(selection):
        values = selection
        if all(isinstance(item, str) for item in values):
            requested = [str(item) for item in values]
            if all(item in ordered_set for item in requested):
                requested_set = set(requested)
                return [item_id for item_id in ordered_ids if item_id in requested_set]
            return []
        if all(isinstance(item, int) and not isinstance(item, bool) for item in values):
            requested_indices: set[int] = set()
            for item in values:
                if isinstance(item, int) and not isinstance(item, bool) and item > 0:
                    requested_indices.add(item)
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
        requested_indices = set(parse_selection_expr(selection, max_index=len(ordered_ids)))
    except ValueError:
        return []

    return [
        item_id for index, item_id in enumerate(ordered_ids, start=1) if index in requested_indices
    ]


def _load_v3_discovery(*, engine: ImportWizardEngine, session_id: str) -> list[dict[str, object]]:
    session_dir = f"import/sessions/{session_id}"
    fs = engine.get_file_service()
    discovery_any = read_json(fs, RootName.WIZARDS, f"{session_dir}/discovery.json")
    if not _is_object_list(discovery_any):
        return []
    return [dict(item) for item in discovery_any if _is_str_object_dict(item)]


def _ordered_ids_from_state(*, state: dict[str, object], step_id: str) -> list[str]:
    vars_state = _as_str_object_dict(state.get("vars"))
    phase1 = _as_str_object_dict(vars_state.get("phase1"))
    prompt_any = phase1.get(step_id)
    prompt = _as_str_object_dict(prompt_any)
    key = "filtered_ids" if step_id == "select_books" else "ordered_ids"
    ordered_ids_any = prompt.get(key)
    if not _is_object_list(ordered_ids_any):
        return []
    return [item for item in ordered_ids_any if isinstance(item, str)]


def _derive_v3_selected_ids(
    *,
    engine: ImportWizardEngine,
    session_id: str,
    step_id: str,
    selection: object,
    state: dict[str, object] | None = None,
) -> list[str]:
    ordered_ids = (
        _ordered_ids_from_state(state=state, step_id=step_id) if isinstance(state, dict) else []
    )
    if ordered_ids:
        return _selection_ids_from_value(ordered_ids=ordered_ids, selection=selection)

    discovery = _load_v3_discovery(engine=engine, session_id=session_id)
    if not discovery:
        return []

    authors_items, books_items = derive_selection_items(discovery)
    items = authors_items if step_id == "select_authors" else books_items
    ordered_ids = [
        str(item.get("item_id")) for item in items if isinstance(item.get("item_id"), str)
    ]
    return _selection_ids_from_value(ordered_ids=ordered_ids, selection=selection)


def _validate_v3_selection_payload(
    *,
    engine: ImportWizardEngine,
    session_id: str,
    step_id: str,
    payload: dict[str, object],
    state: dict[str, object],
) -> None:
    if step_id not in {"select_authors", "select_books"}:
        return
    if "selection" not in payload:
        return

    selection = payload.get("selection")
    discovery = _load_v3_discovery(engine=engine, session_id=session_id)
    if not discovery:
        if selection in (None, "", [], "all", "a", "A"):
            return
        raise StepSubmissionError("selection out of range")

    if selection in (None, "", []):
        raise StepSubmissionError("selection is required")

    selected_ids = _derive_v3_selected_ids(
        engine=engine,
        session_id=session_id,
        step_id=step_id,
        selection=selection,
        state=state,
    )
    if selected_ids:
        return
    raise StepSubmissionError("selection out of range")


def sync_v3_legacy_state(
    *, engine: ImportWizardEngine, session_id: str, state: dict[str, object]
) -> dict[str, object]:
    answers = _as_str_object_dict(state.get("answers"))
    inputs = _as_str_object_dict(state.get("inputs"))

    for mirrored_step_id in (
        "select_authors",
        "select_books",
        "conflict_policy",
        "final_summary_confirm",
    ):
        answer_any = answers.get(mirrored_step_id)
        if _is_str_object_dict(answer_any):
            inputs[mirrored_step_id] = dict(answer_any)

    state["inputs"] = inputs

    authors_any = inputs.get("select_authors")
    if _is_str_object_dict(authors_any):
        state["selected_author_ids"] = _derive_v3_selected_ids(
            engine=engine,
            session_id=session_id,
            step_id="select_authors",
            selection=authors_any.get("selection_expr"),
            state=state,
        )

    books_any = inputs.get("select_books")
    if _is_str_object_dict(books_any):
        state["selected_book_ids"] = _derive_v3_selected_ids(
            engine=engine,
            session_id=session_id,
            step_id="select_books",
            selection=books_any.get("selection_expr"),
            state=state,
        )

    return state


def _needs_v3_plan_refresh(state: dict[str, object]) -> bool:
    computed_any = state.get("computed")
    if _is_str_object_dict(computed_any) and "plan_summary" in computed_any:
        return False

    trace_any = state.get("trace")
    if not _is_object_list(trace_any):
        return False

    return any(
        _is_str_object_dict(entry) and entry.get("step_id") == "plan_preview_batch"
        for entry in trace_any
    )


def _refresh_v3_phase1_authority(
    *,
    effective_model: dict[str, object],
    state: dict[str, object],
    discovery_any: object,
    fs: object,
) -> dict[str, object]:
    if not phase1_session_authority_applies(effective_model=effective_model):
        return state
    if not _is_object_list(discovery_any):
        return state
    discovery = [dict(item) for item in discovery_any if _is_str_object_dict(item)]
    vars_state = _as_str_object_dict(state.get("vars"))
    vars_state["phase1"] = build_phase1_projection(
        discovery=discovery,
        state=state,
        fs=fs,
    )
    state["vars"] = vars_state
    return state


def _sync_v3_author_loop_confirmed(*, state: dict[str, object], step_id: str) -> dict[str, object]:
    if step_id not in {"effective_author_item", "store_author_item"}:
        return state

    answers = _as_str_object_dict(state.get("answers"))
    stored_answer = _as_str_object_dict(answers.get("store_author_item"))
    stored_author = str(stored_answer.get("author") or "").strip()

    vars_state = _as_str_object_dict(state.get("vars"))
    author_loop = _as_str_object_dict(vars_state.get("author_loop"))
    index_any = author_loop.get("index")
    if not isinstance(index_any, int) or isinstance(index_any, bool):
        return state
    selected_index = index_any - 1
    if selected_index < 0:
        return state

    phase1 = _as_str_object_dict(vars_state.get("phase1"))
    select_authors = _as_str_object_dict(phase1.get("select_authors"))
    selected_ids_any = select_authors.get("selected_ids")
    selected_ids = (
        [item for item in selected_ids_any if isinstance(item, str)]
        if _is_object_list(selected_ids_any)
        else []
    )
    if selected_index >= len(selected_ids):
        return state

    if not stored_author:
        labels_any = select_authors.get("selected_author_label_list")
        labels = (
            [item for item in labels_any if isinstance(item, str)]
            if _is_object_list(labels_any)
            else []
        )
        if selected_index < len(labels):
            stored_author = str(labels[selected_index]).strip()
    if not stored_author:
        return state

    selected_author_id = selected_ids[selected_index]
    confirmed = _as_str_object_dict(author_loop.get("confirmed"))
    confirmed[selected_author_id] = stored_author
    author_loop["confirmed"] = confirmed
    vars_state["author_loop"] = author_loop
    state["vars"] = vars_state
    return state


def _sync_v3_title_loop_confirmed(*, state: dict[str, object], step_id: str) -> dict[str, object]:
    if step_id not in {"effective_title_item", "store_title_item"}:
        return state

    answers = _as_str_object_dict(state.get("answers"))
    stored_answer = _as_str_object_dict(answers.get("store_title_item"))
    stored_title = str(stored_answer.get("title") or "").strip()

    vars_state = _as_str_object_dict(state.get("vars"))
    title_loop = _as_str_object_dict(vars_state.get("title_loop"))
    index_any = title_loop.get("index")
    if not isinstance(index_any, int) or isinstance(index_any, bool):
        return state
    selected_index = index_any - 1
    if selected_index < 0:
        return state

    phase1 = _as_str_object_dict(vars_state.get("phase1"))
    select_books = _as_str_object_dict(phase1.get("select_books"))
    selected_ids_any = select_books.get("selected_ids")
    selected_ids = (
        [item for item in selected_ids_any if isinstance(item, str)]
        if _is_object_list(selected_ids_any)
        else []
    )
    if selected_index >= len(selected_ids):
        return state

    if not stored_title:
        labels_any = select_books.get("selected_book_label_list")
        labels = (
            [item for item in labels_any if isinstance(item, str)]
            if _is_object_list(labels_any)
            else []
        )
        if selected_index < len(labels):
            stored_title = str(labels[selected_index]).strip()
    if not stored_title:
        return state

    selected_book_id = selected_ids[selected_index]
    confirmed = _as_str_object_dict(title_loop.get("confirmed"))
    confirmed[selected_book_id] = stored_title
    title_loop["confirmed"] = confirmed
    vars_state["title_loop"] = title_loop
    state["vars"] = vars_state
    return state


def _sync_v3_cover_loop_confirmed(*, state: dict[str, object], step_id: str) -> dict[str, object]:
    if step_id not in {"cover_mode_item", "cover_mode_item_url", "store_cover_item"}:
        return state

    current_step_id = str(state.get("current_step_id") or "")
    if step_id == "cover_mode_item" and current_step_id == "cover_mode_item_url":
        return state

    answers = _as_str_object_dict(state.get("answers"))
    store_answer = _as_str_object_dict(answers.get("store_cover_item"))
    raw_mode = store_answer.get("mode")
    if raw_mode is None:
        raw_mode = _as_str_object_dict(answers.get("cover_mode_item")).get("value")
    mode = str(raw_mode or "").strip().lower()
    if mode not in {"skip", "url", "file", "embedded"}:
        mode = "skip"

    raw_url = store_answer.get("url")
    url = str(raw_url or "").strip()
    if mode == "url" and not url:
        fallback_url = _as_str_object_dict(answers.get("cover_mode_item_url")).get("value")
        url = str(fallback_url or "").strip()

    vars_state = _as_str_object_dict(state.get("vars"))
    cover_loop = _as_str_object_dict(vars_state.get("cover_loop"))
    index_any = cover_loop.get("index")
    if not isinstance(index_any, int) or isinstance(index_any, bool):
        return state
    selected_index = index_any - 1
    if selected_index < 0:
        return state

    phase1 = _as_str_object_dict(vars_state.get("phase1"))
    select_books = _as_str_object_dict(phase1.get("select_books"))
    selected_paths_any = select_books.get("selected_source_relative_paths")
    selected_paths = (
        [item for item in selected_paths_any if isinstance(item, str)]
        if _is_object_list(selected_paths_any)
        else []
    )
    if selected_index >= len(selected_paths):
        return state

    source_relative_path = selected_paths[selected_index]
    confirmed = _as_str_object_dict(cover_loop.get("confirmed"))
    if mode == "url":
        confirmed[source_relative_path] = {"kind": "url", "url": url}
    elif mode in {"file", "embedded"}:
        confirmed[source_relative_path] = {"kind": mode}
    else:
        confirmed[source_relative_path] = {"kind": "skip"}
    cover_loop["confirmed"] = confirmed
    vars_state["cover_loop"] = cover_loop
    state["vars"] = vars_state
    return state


def submit_step_impl(
    *,
    engine: ImportWizardEngine,
    session_id: str,
    step_id: str,
    payload: dict[str, object],
) -> dict[str, object]:
    try:
        state = engine.load_state(session_id)
        phase_any = state.get("phase")
        phase = phase_any if isinstance(phase_any, int) else 1
        if phase == 2:
            return invariant_violation(
                message="session is locked (phase 2)",
                path="$.phase",
                reason="phase_locked",
                meta={},
            )
        if state.get("status") != "in_progress":
            raise StepSubmissionError("session is not in progress")

        emit_required_event(
            "step.submit",
            "step.submit",
            {
                "session_id": session_id,
                "step_id": step_id,
                "model_fingerprint": state.get("model_fingerprint"),
                "discovery_fingerprint": _as_str_object_dict(state.get("derived")).get(
                    "discovery_fingerprint"
                ),
                "effective_config_fingerprint": _as_str_object_dict(state.get("derived")).get(
                    "effective_config_fingerprint"
                ),
            },
        )

        effective_model = engine.load_effective_model(session_id)
        if is_v3_effective_model(effective_model):
            _validate_v3_selection_payload(
                engine=engine,
                session_id=session_id,
                step_id=step_id,
                payload=payload,
                state=state,
            )
            next_state = submit_current_step(
                effective_model=effective_model,
                state=state,
                session_id=session_id,
                step_id=step_id,
                payload=payload,
            )
            next_state = sync_v3_legacy_state(
                engine=engine,
                session_id=session_id,
                state=next_state,
            )
            next_state = _sync_v3_author_loop_confirmed(state=next_state, step_id=step_id)
            next_state = _sync_v3_title_loop_confirmed(state=next_state, step_id=step_id)
            next_state = _sync_v3_cover_loop_confirmed(state=next_state, step_id=step_id)
            session_dir = f"import/sessions/{session_id}"
            fs = engine.get_file_service()
            discovery_any = read_json(fs, RootName.WIZARDS, f"{session_dir}/discovery.json")
            next_state = _refresh_v3_phase1_authority(
                effective_model=effective_model,
                state=next_state,
                discovery_any=discovery_any,
                fs=fs,
            )

            next_state = run_automatic_steps(
                effective_model=effective_model,
                state=next_state,
                session_id=session_id,
            )
            next_state = sync_v3_legacy_state(
                engine=engine,
                session_id=session_id,
                state=next_state,
            )
            next_state = _sync_v3_author_loop_confirmed(state=next_state, step_id=step_id)
            next_state = _sync_v3_title_loop_confirmed(state=next_state, step_id=step_id)
            next_state = _sync_v3_cover_loop_confirmed(state=next_state, step_id=step_id)
            next_state = _refresh_v3_phase1_authority(
                effective_model=effective_model,
                state=next_state,
                discovery_any=discovery_any,
                fs=fs,
            )
            next_state["updated_at"] = iso_utc_now()
            engine.persist_state(session_id, next_state)
            if _needs_v3_plan_refresh(next_state):
                engine.compute_plan(session_id)
                next_state = engine.load_state(session_id)
            engine.append_decision(
                session_id,
                step_id=step_id,
                payload=dict(payload),
                result="accepted",
                error=None,
            )
            return next_state
        steps_any = effective_model.get("steps")
        if not _is_object_list(steps_any):
            raise StepSubmissionError("effective model missing steps")
        steps = [s for s in steps_any if _is_str_object_dict(s)]
        flow_cfg_norm = engine.load_effective_flow_config(session_id)

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

        normalized_payload = engine.validate_and_canonicalize_payload(
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

        answers = _as_str_object_dict(state.get("answers"))
        answers[step_id] = normalized_payload
        state["answers"] = answers

        # Backward compatibility: maintain legacy inputs mirror.
        inputs = _as_str_object_dict(state.get("inputs"))
        inputs[step_id] = normalized_payload
        state["inputs"] = inputs

        if step_id == "select_authors":
            sel = normalized_payload.get("selection")
            if _is_object_list(sel):
                selection_items = sel
                selected_author_ids = [item for item in selection_items if isinstance(item, str)]
                if len(selected_author_ids) == len(selection_items):
                    state["selected_author_ids"] = selected_author_ids

        if step_id == "select_books":
            sel = normalized_payload.get("selection")
            if _is_object_list(sel):
                selection_items = sel
                selected_book_ids = [item for item in selection_items if isinstance(item, str)]
                if len(selected_book_ids) == len(selection_items):
                    state["selected_book_ids"] = selected_book_ids

        if step_id == "effective_author_title":
            state["effective_author_title"] = _as_str_object_dict(normalized_payload)

        completed_any = state.get("completed_step_ids")
        completed = (
            [item for item in completed_any if isinstance(item, str)]
            if _is_object_list(completed_any)
            else []
        )
        if step_id not in completed:
            completed.append(step_id)
        state["completed_step_ids"] = completed

        next_step = engine.next_step_after_submit(
            step_id=step_id,
            state=state,
            flow_cfg_norm=flow_cfg_norm,
        )

        state["current_step_id"] = engine.auto_advance_computed_steps(
            session_id=session_id,
            state=state,
            next_step_id=next_step,
            flow_cfg_norm=flow_cfg_norm,
        )
        sync_session_cursor(state, step_id=str(state.get("current_step_id") or ""))

        state["updated_at"] = iso_utc_now()
        engine.append_decision(
            session_id,
            step_id=step_id,
            payload=normalized_payload,
            result="accepted",
            error=None,
        )
        engine.persist_state(session_id, state)
        return state
    except Exception as e:
        engine.append_decision(
            session_id,
            step_id=step_id,
            payload=dict(payload),
            result="rejected",
            error={
                "type": e.__class__.__name__,
                "message": ascii_message(str(e) or e.__class__.__name__),
            },
        )
        return exception_envelope(e)


_sync_v3_legacy_state = sync_v3_legacy_state
