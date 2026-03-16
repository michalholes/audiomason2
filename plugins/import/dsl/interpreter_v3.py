"""Interpreter runtime for WizardDefinition v3.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from ..engine_util import _emit_required, append_trace_event, sync_session_cursor
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


def _state_view(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "answers": dict(state.get("answers") or {}),
        "vars": dict(state.get("vars") or {}),
        "jobs": dict(state.get("jobs") or {}),
        "status": state.get("status"),
        "cursor": dict(state.get("cursor") or {}),
    }


def _resolve_expr(
    expr_ref: dict[str, Any],
    *,
    state: dict[str, Any],
    inputs: dict[str, Any],
    op_outputs: dict[str, Any] | None,
    allow_op_outputs: bool,
    path: str,
) -> Any:
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
        if isinstance(error, dict) and isinstance(error.get("reason"), str):
            reason = str(error.get("reason"))
        raise FinalizeError(reason)
    return value


def resolve_inputs(step: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    raw_inputs = step.get("inputs")
    if not isinstance(raw_inputs, dict):
        return {}

    primitive_id = str(step.get("primitive_id") or "")
    primitive_version = int(step.get("primitive_version") or 0)
    prompt_ui: dict[str, Any] | None = None
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
    out: dict[str, Any] = {}
    for key, value in raw_inputs.items():
        if key in prompt_keys:
            continue
        if phase2:
            out[str(key)] = resolve_phase2_input_value(
                value,
                state=state,
                inputs={**current_inputs, **out},
                path=f"$.inputs.{key}",
            )
            continue
        if isinstance(value, dict) and set(value.keys()) == {"expr"}:
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


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    if path.startswith("$.state.answers."):
        parts = path[len("$.state.answers.") :].split(".")
        base: dict[str, Any] = target.setdefault("answers", {})
    elif path.startswith("$.state.vars."):
        parts = path[len("$.state.vars.") :].split(".")
        base = target.setdefault("vars", {})
    else:
        raise FinalizeError("invalid_write_target")

    cur: dict[str, Any] = base
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def apply_writes(
    *,
    state: dict[str, Any],
    step: dict[str, Any],
    inputs: dict[str, Any],
    op_outputs: dict[str, Any],
) -> dict[str, Any]:
    writes_any = step.get("writes")
    if not isinstance(writes_any, list) or not writes_any:
        return state

    updated = dict(state)
    updated["answers"] = dict(state.get("answers") or {})
    updated["vars"] = dict(state.get("vars") or {})
    for i, write_any in enumerate(writes_any):
        if not isinstance(write_any, dict):
            raise FinalizeError("invalid_write")
        to_path = write_any.get("to_path")
        if not isinstance(to_path, str) or not to_path:
            raise FinalizeError("invalid_write_target")
        value = write_any.get("value")
        if isinstance(value, dict) and set(value.keys()) == {"expr"}:
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
    effective_model: dict[str, Any],
    step_id: str,
    state: dict[str, Any],
) -> str | None:
    edges_any = effective_model.get("edges")
    if not isinstance(edges_any, list):
        return None
    unconditional: str | None = None
    for edge_any in edges_any:
        if not isinstance(edge_any, dict) or edge_any.get("from") != step_id:
            continue
        to = edge_any.get("to")
        if not isinstance(to, str) or not to:
            continue
        cond = edge_any.get("condition_expr")
        if cond is None:
            if unconditional is None:
                unconditional = to
            continue
        if isinstance(cond, dict) and set(cond.keys()) == {"expr"}:
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
    step: dict[str, Any],
    state: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    inputs = resolve_inputs(step, state)
    if inputs.get("autofill_if") is not True:
        return None

    key = prompt_output_key(
        str(step.get("primitive_id") or ""),
        int(step.get("primitive_version") or 0),
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
            int(step.get("primitive_version") or 0),
            {key: candidate},
        )
    except ValueError as exc:
        raise FinalizeError(str(exc)) from exc
    return inputs, outputs


def _advance_prompt_step(
    *,
    effective_model: dict[str, Any],
    state: dict[str, Any],
    step_id: str,
    step: dict[str, Any],
    inputs: dict[str, Any],
    outputs: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    primitive_id = str(step.get("primitive_id") or "")
    primitive_version = int(step.get("primitive_version") or 0)
    state = apply_writes(state=state, step=step, inputs=inputs, op_outputs=outputs)
    completed = list(state.get("completed_step_ids") or [])
    if step_id not in completed:
        completed.append(step_id)
    state["completed_step_ids"] = completed
    next_step = _next_step_id(effective_model, step_id, state)
    state["current_step_id"] = step_id if next_step is None else next_step
    sync_session_cursor(state, step_id=state["current_step_id"])
    writes_any = step.get("writes")
    writes = (
        [str(item.get("to_path")) for item in writes_any if isinstance(item, dict)]
        if isinstance(writes_any, list)
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


def _runtime_diag_context(state: dict[str, Any], session_id: str) -> dict[str, Any]:
    derived_any = state.get("derived")
    derived = dict(derived_any) if isinstance(derived_any, dict) else {}
    return {
        "session_id": session_id,
        "model_fingerprint": str(state.get("model_fingerprint") or ""),
        "discovery_fingerprint": str(derived.get("discovery_fingerprint") or ""),
        "effective_config_fingerprint": str(derived.get("effective_config_fingerprint") or ""),
    }


def _emit_runtime_boundary(
    *,
    event: str,
    state: dict[str, Any],
    session_id: str,
    step_id: str,
    primitive_id: str,
    primitive_version: int,
    error: Exception | None = None,
) -> None:
    data: dict[str, Any] = {
        "session_id": session_id,
        "step_id": step_id,
        "primitive_id": primitive_id,
        "primitive_version": primitive_version,
    }
    if error is not None:
        data["error_type"] = error.__class__.__name__
        data["error_message"] = str(error) or error.__class__.__name__
    _emit_required(
        event=event,
        operation="runtime.boundary",
        data={**_runtime_diag_context(state, session_id), **data},
    )


def _enter_phase2_boundary(*, state: dict[str, Any], step_id: str) -> dict[str, Any]:
    state["phase"] = 2
    state["current_step_id"] = step_id
    sync_session_cursor(state, step_id=step_id)
    return state


def prompt_ui_from_resolved_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    return {key: inputs[key] for key in PROMPT_METADATA_KEYS if key in inputs}


def _registry_declares_primitive(primitive_id: str, primitive_version: int) -> bool:
    return any(
        str(entry.get("primitive_id") or "") == primitive_id
        and int(entry.get("version") or 0) == primitive_version
        for entry in baseline_registry_entries()
    )


def run_automatic_steps(
    *,
    effective_model: dict[str, Any],
    state: dict[str, Any],
    session_id: str,
) -> dict[str, Any]:
    current = str((state.get("cursor") or {}).get("step_id") or state.get("current_step_id") or "")
    while current and state.get("status") == "in_progress":
        step = get_step(effective_model, current)
        if int(step.get("phase") or 1) == 2:
            return _enter_phase2_boundary(state=state, step_id=current)
        primitive_id = str(step.get("primitive_id") or "")
        primitive_version = int(step.get("primitive_version") or 0)
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
        try:
            phase2 = execute_phase2_step(
                effective_model=effective_model,
                state=state,
                session_id=session_id,
                step_id=current,
                step=step,
                inputs=inputs,
                run_graph=(
                    lambda model, graph_state, graph_session_id: run_automatic_steps(
                        effective_model=model,
                        state=graph_state,
                        session_id=graph_session_id,
                    )
                ),
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
            [str(item.get("to_path")) for item in writes_any if isinstance(item, dict)]
            if isinstance(writes_any, list)
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
        state["current_step_id"] = current if next_step is None else next_step
        sync_session_cursor(state, step_id=state["current_step_id"])
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
    effective_model: dict[str, Any],
    state: dict[str, Any],
    session_id: str,
    step_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if state.get("status") != "in_progress":
        raise FinalizeError("status_not_in_progress")
    current = str((state.get("cursor") or {}).get("step_id") or state.get("current_step_id") or "")
    if step_id != current:
        raise StepSubmissionError("step_id must match current_step_id")
    step = get_step(effective_model, step_id)
    primitive_id = str(step.get("primitive_id") or "")
    primitive_version = int(step.get("primitive_version") or 0)
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
