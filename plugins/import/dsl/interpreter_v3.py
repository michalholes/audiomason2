"""Interpreter runtime for WizardDefinition v3.

ASCII-only.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TypeGuard, cast

from ..engine_util import append_trace_event, emit_required_event, sync_session_cursor
from ..errors import FinalizeError, StepSubmissionError
from ..primitives import (
    CTRL_STOP_ID,
    baseline_registry_entries,
    execute_non_prompt,
    is_non_interactive,
    is_prompt_primitive,
    validate_submit_payload,
)
from ..primitives.ui_v1 import (
    PROMPT_METADATA_KEYS,
    normalize_prompt_ui,
    project_prompt_ui,
    prompt_output_key,
)
from .expr_eval import eval_expr_ref
from .flowmodel_v3 import get_step
from .subflow_runtime import (
    execute_phase2_step,
    guard_parallel_map_write_conflicts,
    record_trace,
    resolve_phase2_input_value,
    runtime_input_context,
)


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _as_str_list(value: object) -> list[str]:
    if not _is_object_list(value):
        return []
    return [item for item in value if isinstance(item, str)]


def _to_int_or_default(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _state_view(state: dict[str, object]) -> dict[str, object]:
    return {
        "answers": _as_str_object_dict(state.get("answers")),
        "vars": _as_str_object_dict(state.get("vars")),
        "jobs": _as_str_object_dict(state.get("jobs")),
        "source": _as_str_object_dict(state.get("source")),
        "status": state.get("status"),
        "cursor": _as_str_object_dict(state.get("cursor")),
    }


def _resolve_expr(
    expr_ref: dict[str, object],
    *,
    state: dict[str, object],
    inputs: dict[str, object],
    op_outputs: dict[str, object] | None,
    allow_op_outputs: bool,
    path: str,
) -> object:
    ok, value, error = eval_expr_ref(
        expr_ref,
        state=_state_view(state),
        inputs=inputs,
        op_outputs=op_outputs,
        allow_op_outputs=allow_op_outputs,
        path=path,
    )
    if not ok:
        reason = "expr_error"
        if _is_str_object_dict(error) and isinstance(error.get("reason"), str):
            reason = str(error.get("reason"))
        raise FinalizeError(reason)
    return value


def resolve_inputs(step: dict[str, object], state: dict[str, object]) -> dict[str, object]:
    raw_inputs = step.get("inputs")
    if not _is_str_object_dict(raw_inputs):
        return {}

    primitive_id = str(step.get("primitive_id") or "")
    primitive_version = _to_int_or_default(step.get("primitive_version"), 0)
    prompt_ui: dict[str, object] | None = None
    prompt_keys: set[str] = set()
    if is_prompt_primitive(primitive_id, primitive_version):
        try:
            prompt_ui = project_prompt_ui(primitive_id, primitive_version, raw_inputs)
        except ValueError as exc:
            raise FinalizeError(str(exc)) from exc
        prompt_keys = set(prompt_ui or {})
    elif primitive_id == "ui.message" and primitive_version == 1:
        prompt_keys = set(PROMPT_METADATA_KEYS)

    phase2 = (primitive_id, primitive_version) in {
        ("parallel.fork_join", 1),
        ("flow.invoke", 1),
        ("flow.loop", 1),
    }
    current_inputs = runtime_input_context(state)
    out: dict[str, object] = {}
    for key, value in raw_inputs.items():
        if key in prompt_keys:
            continue
        if primitive_id == "call.invoke" and key == "args" and _is_str_object_dict(value):
            out[str(key)] = resolve_phase2_input_value(
                value,
                state=state,
                inputs={**current_inputs, **out},
                path=f"$.inputs.{key}",
            )
            continue
        if primitive_id == "flow.loop" and key == "param_bindings" and _is_object_list(value):
            out[str(key)] = deepcopy(value)
            continue
        if primitive_id in {"data.filter", "data.map", "data.group_by"} and key in {
            "condition_expr",
            "key_expr",
            "value_expr",
        }:
            out[str(key)] = deepcopy(value)
            continue
        if phase2:
            out[str(key)] = resolve_phase2_input_value(
                value,
                state=state,
                inputs={**current_inputs, **out},
                path=f"$.inputs.{key}",
            )
            continue
        if _is_str_object_dict(value) and set(value.keys()) == {"expr"}:
            out[str(key)] = _resolve_expr(
                value,
                state=state,
                inputs={**current_inputs, **out},
                op_outputs=None,
                allow_op_outputs=False,
                path=f"$.inputs.{key}",
            )
            continue
        out[str(key)] = value

    if prompt_ui:
        try:
            prompt_inputs = normalize_prompt_ui(
                primitive_id,
                primitive_version,
                prompt_ui,
                resolve_expr=lambda expr_ref, path, metadata: _resolve_expr(
                    expr_ref,
                    state=state,
                    inputs={**current_inputs, **out, **metadata},
                    op_outputs=None,
                    allow_op_outputs=False,
                    path=path,
                ),
                path_prefix="$.inputs",
            )
        except ValueError as exc:
            raise FinalizeError(str(exc)) from exc
        out.update(prompt_inputs)
    return out


def _set_path(target: dict[str, object], path: str, value: object) -> None:
    if path.startswith("$.state.answers."):
        parts = path[len("$.state.answers.") :].split(".")
        answers = _as_str_object_dict(target.get("answers"))
        target["answers"] = answers
        base: dict[str, object] = answers
    elif path.startswith("$.state.vars."):
        parts = path[len("$.state.vars.") :].split(".")
        vars_doc = _as_str_object_dict(target.get("vars"))
        target["vars"] = vars_doc
        base = vars_doc
    else:
        raise FinalizeError("invalid_write_target")

    cur: dict[str, object] = base
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not _is_str_object_dict(nxt):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def apply_writes(
    *,
    state: dict[str, object],
    step: dict[str, object],
    inputs: dict[str, object],
    op_outputs: dict[str, object],
) -> dict[str, object]:
    writes_any = step.get("writes")
    if not _is_object_list(writes_any) or not writes_any:
        return state

    updated = dict(state)
    updated["answers"] = _as_str_object_dict(state.get("answers"))
    updated["vars"] = _as_str_object_dict(state.get("vars"))
    for i, write_any in enumerate(writes_any):
        if not _is_str_object_dict(write_any):
            raise FinalizeError("invalid_write")
        to_path = write_any.get("to_path")
        if not isinstance(to_path, str) or not to_path:
            raise FinalizeError("invalid_write_target")
        value = write_any.get("value")
        if _is_str_object_dict(value) and set(value.keys()) == {"expr"}:
            value = _resolve_expr(
                value,
                state=updated,
                inputs=inputs,
                op_outputs=op_outputs,
                allow_op_outputs=True,
                path=f"$.writes[{i}].value",
            )
        _set_path(updated, to_path, value)
    return updated


def _next_step_id(
    effective_model: dict[str, object],
    step_id: str,
    state: dict[str, object],
) -> str | None:
    edges_any = effective_model.get("edges")
    if not _is_object_list(edges_any):
        return None
    unconditional: str | None = None
    for edge_any in edges_any:
        if not _is_str_object_dict(edge_any) or edge_any.get("from") != step_id:
            continue
        to = edge_any.get("to")
        if not isinstance(to, str) or not to:
            continue
        cond = edge_any.get("condition_expr")
        if cond is None:
            if unconditional is None:
                unconditional = to
            continue
        if _is_str_object_dict(cond) and set(cond.keys()) == {"expr"}:
            value = _resolve_expr(
                cond,
                state=state,
                inputs=runtime_input_context(state),
                op_outputs=None,
                allow_op_outputs=False,
                path="$.condition_expr",
            )
            if value is True:
                return to
    return unconditional


def _prompt_autofill_outputs(
    step: dict[str, object],
    state: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]] | None:
    inputs = resolve_inputs(step, state)
    if inputs.get("autofill_if") is not True:
        return None

    key = prompt_output_key(
        str(step.get("primitive_id") or ""),
        _to_int_or_default(step.get("primitive_version"), 0),
    )
    if not isinstance(key, str) or not key:
        return None

    if "prefill" in inputs:
        candidate = inputs["prefill"]
    elif "default_value" in inputs:
        candidate = inputs["default_value"]
    else:
        return None

    try:
        outputs = validate_submit_payload(
            str(step.get("primitive_id") or ""),
            _to_int_or_default(step.get("primitive_version"), 0),
            {key: candidate},
        )
    except ValueError as exc:
        raise FinalizeError(str(exc)) from exc
    return inputs, outputs


def _advance_prompt_step(
    *,
    effective_model: dict[str, object],
    state: dict[str, object],
    step_id: str,
    step: dict[str, object],
    inputs: dict[str, object],
    outputs: dict[str, object],
) -> tuple[dict[str, object], str | None]:
    primitive_id = str(step.get("primitive_id") or "")
    primitive_version = _to_int_or_default(step.get("primitive_version"), 0)
    state = apply_writes(state=state, step=step, inputs=inputs, op_outputs=outputs)
    completed = _as_str_list(state.get("completed_step_ids"))
    if step_id not in completed:
        completed.append(step_id)
    state["completed_step_ids"] = completed
    next_step = _next_step_id(effective_model, step_id, state)
    current_step_id = step_id if next_step is None else next_step
    state["current_step_id"] = current_step_id
    sync_session_cursor(state, step_id=current_step_id)
    writes_any = step.get("writes")
    writes = (
        [str(item.get("to_path")) for item in writes_any if _is_str_object_dict(item)]
        if _is_object_list(writes_any)
        else []
    )
    state = record_trace(
        state,
        step_id=step_id,
        primitive_id=primitive_id,
        primitive_version=primitive_version,
        result="OK",
        writes=writes,
        append_trace=append_trace_event,
    )
    return state, next_step


def _runtime_diag_context(state: dict[str, object], session_id: str) -> dict[str, object]:
    derived = _as_str_object_dict(state.get("derived"))
    return {
        "session_id": session_id,
        "model_fingerprint": str(state.get("model_fingerprint") or ""),
        "discovery_fingerprint": str(derived.get("discovery_fingerprint") or ""),
        "effective_config_fingerprint": str(derived.get("effective_config_fingerprint") or ""),
    }


def _emit_runtime_boundary(
    *,
    event: str,
    state: dict[str, object],
    session_id: str,
    step_id: str,
    primitive_id: str,
    primitive_version: int,
    error: Exception | None = None,
) -> None:
    data: dict[str, object] = {
        "session_id": session_id,
        "step_id": step_id,
        "primitive_id": primitive_id,
        "primitive_version": primitive_version,
    }
    if error is not None:
        data["error_type"] = error.__class__.__name__
        data["error_message"] = str(error) or error.__class__.__name__
    emit_required_event(
        event=event,
        operation="runtime.boundary",
        data={**_runtime_diag_context(state, session_id), **data},
    )


def _enter_phase2_boundary(*, state: dict[str, object], step_id: str) -> dict[str, object]:
    state["phase"] = 2
    state["current_step_id"] = step_id
    sync_session_cursor(state, step_id=step_id)
    return state


def prompt_ui_from_resolved_inputs(inputs: dict[str, object]) -> dict[str, object]:
    return {key: inputs[key] for key in PROMPT_METADATA_KEYS if key in inputs}


def _registry_declares_primitive(primitive_id: str, primitive_version: int) -> bool:
    return any(
        str(entry.get("primitive_id") or "") == primitive_id
        and _to_int_or_default(entry.get("version"), 0) == primitive_version
        for entry in baseline_registry_entries()
    )


def run_automatic_steps(
    *,
    effective_model: dict[str, object],
    state: dict[str, object],
    session_id: str,
) -> dict[str, object]:
    cursor = _as_str_object_dict(state.get("cursor"))
    current = str(cursor.get("step_id") or state.get("current_step_id") or "")
    while current and state.get("status") == "in_progress":
        step = get_step(effective_model, current)
        if _to_int_or_default(step.get("phase"), 1) == 2:
            return _enter_phase2_boundary(state=state, step_id=current)
        primitive_id = str(step.get("primitive_id") or "")
        primitive_version = _to_int_or_default(step.get("primitive_version"), 0)
        if is_prompt_primitive(primitive_id, primitive_version):
            prompt_outputs = _prompt_autofill_outputs(step, state)
            if prompt_outputs is None:
                break
            inputs, outputs = prompt_outputs
            state, next_step = _advance_prompt_step(
                effective_model=effective_model,
                state=state,
                step_id=current,
                step=step,
                inputs=inputs,
                outputs=outputs,
            )
            if next_step is None:
                break
            current = next_step
            continue
        if not is_non_interactive(primitive_id, primitive_version):
            raise FinalizeError("non_prompt_submit_payload_forbidden")
        if not _registry_declares_primitive(primitive_id, primitive_version):
            raise FinalizeError("unknown primitive")
        inputs = resolve_inputs(step, state)
        guard_parallel_map_write_conflicts(step, inputs)
        writes_applied = False
        _emit_runtime_boundary(
            event="diag.boundary.start",
            state=state,
            session_id=session_id,
            step_id=current,
            primitive_id=primitive_id,
            primitive_version=primitive_version,
        )

        def _run_graph(
            graph: dict[str, object],
            state: dict[str, object],
            session_id: str,
        ) -> dict[str, object]:
            return run_automatic_steps(
                effective_model=graph,
                state=state,
                session_id=session_id,
            )

        try:
            phase2 = execute_phase2_step(
                effective_model=effective_model,
                state=state,
                session_id=session_id,
                step_id=current,
                step=step,
                inputs=inputs,
                run_graph=_run_graph,
                apply_writes=apply_writes,
                append_trace=append_trace_event,
            )
            if phase2 is None:
                outputs, jobs = execute_non_prompt(
                    session_id=session_id,
                    step_id=current,
                    primitive_id=primitive_id,
                    primitive_version=primitive_version,
                    inputs=inputs,
                    state=state,
                )
            else:
                state, outputs, jobs, writes_applied = phase2
        except Exception as exc:
            _emit_runtime_boundary(
                event="diag.boundary.fail",
                state=state,
                session_id=session_id,
                step_id=current,
                primitive_id=primitive_id,
                primitive_version=primitive_version,
                error=exc,
            )
            raise
        _emit_runtime_boundary(
            event="diag.boundary.end",
            state=state,
            session_id=session_id,
            step_id=current,
            primitive_id=primitive_id,
            primitive_version=primitive_version,
        )
        state["jobs"] = jobs
        if not writes_applied:
            state = apply_writes(state=state, step=step, inputs=inputs, op_outputs=outputs)
        writes_any = step.get("writes")
        writes = (
            [str(item.get("to_path")) for item in writes_any if _is_str_object_dict(item)]
            if _is_object_list(writes_any)
            else []
        )
        if primitive_id == CTRL_STOP_ID:
            state["status"] = "completed"
            state["current_step_id"] = current
            sync_session_cursor(state, step_id=current)
            return record_trace(
                state,
                step_id=current,
                primitive_id=primitive_id,
                primitive_version=primitive_version,
                result="OK",
                writes=writes,
                append_trace=append_trace_event,
            )
        next_step = _next_step_id(effective_model, current, state)
        current_step_id = current if next_step is None else next_step
        state["current_step_id"] = current_step_id
        sync_session_cursor(state, step_id=current_step_id)
        state = record_trace(
            state,
            step_id=current,
            primitive_id=primitive_id,
            primitive_version=primitive_version,
            result="OK",
            writes=writes,
            append_trace=append_trace_event,
        )
        if next_step is None:
            break
        current = next_step
    return state


def submit_current_step(
    *,
    effective_model: dict[str, object],
    state: dict[str, object],
    session_id: str,
    step_id: str,
    payload: dict[str, object],
) -> dict[str, object]:
    if state.get("status") != "in_progress":
        raise FinalizeError("status_not_in_progress")
    cursor = _as_str_object_dict(state.get("cursor"))
    current = str(cursor.get("step_id") or state.get("current_step_id") or "")
    if step_id != current:
        raise StepSubmissionError("step_id must match current_step_id")
    step = get_step(effective_model, step_id)
    primitive_id = str(step.get("primitive_id") or "")
    primitive_version = _to_int_or_default(step.get("primitive_version"), 0)
    if not is_prompt_primitive(primitive_id, primitive_version):
        raise StepSubmissionError("non-prompt primitive cannot be submitted")
    outputs = validate_submit_payload(primitive_id, primitive_version, payload)
    inputs = resolve_inputs(step, state)
    state, next_step = _advance_prompt_step(
        effective_model=effective_model,
        state=state,
        step_id=step_id,
        step=step,
        inputs=inputs,
        outputs=outputs,
    )
    if next_step is None:
        return state
    return run_automatic_steps(effective_model=effective_model, state=state, session_id=session_id)


__all__ = [
    "prompt_ui_from_resolved_inputs",
    "resolve_inputs",
    "run_automatic_steps",
    "submit_current_step",
]
