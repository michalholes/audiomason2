"""Phase II subflow and fork/join runtime helpers for import DSL.

ASCII-only.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from ..errors import FinalizeError
from .expr_eval import eval_expr_ref
from .loop_runtime import execute_loop

RunGraph = Callable[[dict[str, Any], dict[str, Any], str], dict[str, Any]]
ApplyWrites = Callable[..., dict[str, Any]]
AppendTrace = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]

_RESERVED_VAR_NAMESPACES = {"branches", "subflows", "loops"}


def _state_view(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "answers": dict(state.get("answers") or {}),
        "vars": dict(state.get("vars") or {}),
        "jobs": dict(state.get("jobs") or {}),
        "source": dict(state.get("source") or {}),
        "status": state.get("status"),
        "cursor": dict(state.get("cursor") or {}),
    }


def _resolve_expr(
    expr_ref: dict[str, Any],
    *,
    state: dict[str, Any],
    inputs: dict[str, Any],
    path: str,
) -> Any:
    ok, value, error = eval_expr_ref(
        expr_ref,
        state=_state_view(state),
        inputs=inputs,
        op_outputs=None,
        allow_op_outputs=False,
        path=path,
    )
    if ok:
        return value
    reason = "expr_error"
    if isinstance(error, dict) and isinstance(error.get("reason"), str):
        reason = str(error.get("reason"))
    raise FinalizeError(reason)


def runtime_input_context(state: dict[str, Any]) -> dict[str, Any]:
    vars_any = state.get("vars")
    vars_dict = dict(vars_any) if isinstance(vars_any, dict) else {}
    subflows = dict(vars_dict.get("subflows") or {})
    current = subflows.get("_current_inputs")
    return dict(current) if isinstance(current, dict) else {}


def resolve_phase2_input_value(
    value: Any,
    *,
    state: dict[str, Any],
    inputs: dict[str, Any],
    path: str,
) -> Any:
    if isinstance(value, dict):
        if set(value.keys()) == {"expr"}:
            return _resolve_expr(value, state=state, inputs=inputs, path=path)
        return {
            str(key): resolve_phase2_input_value(
                item,
                state=state,
                inputs=inputs,
                path=f"{path}.{key}",
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            resolve_phase2_input_value(
                item,
                state=state,
                inputs=inputs,
                path=f"{path}[{index}]",
            )
            for index, item in enumerate(value)
        ]
    return value


def ensure_phase2_namespaces(
    state: dict[str, Any],
    *namespaces: str,
) -> dict[str, Any]:
    vars_any = state.get("vars")
    vars_dict = dict(vars_any) if isinstance(vars_any, dict) else {}
    targets = namespaces or tuple(sorted(_RESERVED_VAR_NAMESPACES))
    for key in targets:
        if key not in _RESERVED_VAR_NAMESPACES:
            raise FinalizeError("phase2_namespace_invalid")
        current = vars_dict.get(key)
        vars_dict[key] = dict(current) if isinstance(current, dict) else {}
    state["vars"] = vars_dict
    return state


def _library_id(
    libraries: dict[str, Any],
    *,
    target_library: str,
    target_subflow: str,
) -> str:
    if target_subflow in libraries:
        if target_library and target_library != target_subflow and target_library in libraries:
            raise FinalizeError("subflow_target_ambiguous")
        return target_subflow
    if target_library in libraries:
        return target_library
    raise FinalizeError("subflow_target_not_found")


def _bindings_map(bindings_any: Any) -> dict[str, Any]:
    if not isinstance(bindings_any, list):
        raise FinalizeError("subflow_bindings_invalid")
    out: dict[str, Any] = {}
    for item in bindings_any:
        if not isinstance(item, dict):
            raise FinalizeError("subflow_bindings_invalid")
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise FinalizeError("subflow_bindings_invalid")
        if name in out:
            raise FinalizeError("subflow_bindings_duplicate")
        out[name] = deepcopy(item.get("value"))
    return out


def _set_current_inputs(state: dict[str, Any], bindings: dict[str, Any]) -> dict[str, Any] | None:
    state = ensure_phase2_namespaces(state, "subflows")
    subflows = dict((state.get("vars") or {}).get("subflows") or {})
    previous = subflows.get("_current_inputs")
    previous_dict = dict(previous) if isinstance(previous, dict) else None
    subflows["_current_inputs"] = dict(bindings)
    state["vars"]["subflows"] = subflows
    return previous_dict


def _restore_current_inputs(state: dict[str, Any], previous: dict[str, Any] | None) -> None:
    state = ensure_phase2_namespaces(state, "subflows")
    subflows = dict((state.get("vars") or {}).get("subflows") or {})
    if previous is None:
        subflows.pop("_current_inputs", None)
    else:
        subflows["_current_inputs"] = dict(previous)
    state["vars"]["subflows"] = subflows


def execute_flow_invoke(
    *,
    effective_model: dict[str, Any],
    state: dict[str, Any],
    session_id: str,
    step_id: str,
    inputs: dict[str, Any],
    run_graph: RunGraph,
) -> tuple[dict[str, Any], dict[str, Any]]:
    libraries_any = effective_model.get("libraries")
    libraries = dict(libraries_any) if isinstance(libraries_any, dict) else {}
    target_library = str(inputs.get("target_library") or "")
    target_subflow = str(inputs.get("target_subflow") or "")
    library_id = _library_id(
        libraries,
        target_library=target_library,
        target_subflow=target_subflow,
    )
    library_any = libraries.get(library_id)
    if not isinstance(library_any, dict):
        raise FinalizeError("subflow_target_invalid")
    bindings = _bindings_map(inputs.get("param_bindings"))
    state = ensure_phase2_namespaces(state, "subflows")
    saved_status = state.get("status")
    saved_current = str(state.get("current_step_id") or "")
    saved_cursor = dict(state.get("cursor") or {})
    previous_inputs = _set_current_inputs(state, bindings)
    state["status"] = "in_progress"
    entry_step_id = str(library_any.get("entry_step_id") or "")
    state["current_step_id"] = entry_step_id
    state["cursor"] = {"step_id": entry_step_id}
    subflows = dict((state.get("vars") or {}).get("subflows") or {})
    subflows[step_id] = {
        "target_library": library_id,
        "target_subflow": target_subflow,
        "param_bindings": dict(bindings),
    }
    state["vars"]["subflows"] = subflows
    try:
        state = run_graph(dict(library_any), state, session_id)
        return_values = resolve_phase2_input_value(
            dict(library_any.get("returns") or {}),
            state=state,
            inputs=bindings,
            path=f"$.libraries.{library_id}.returns",
        )
    finally:
        _restore_current_inputs(state, previous_inputs)
        state["status"] = saved_status
        state["current_step_id"] = saved_current
        state["cursor"] = saved_cursor
    return state, {
        "target_library": library_id,
        "target_subflow": target_subflow,
        "param_bindings": dict(bindings),
        "returns": return_values,
    }


def _merge_dicts(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in incoming.items():
        if key in _RESERVED_VAR_NAMESPACES:
            continue
        if key not in merged:
            merged[key] = deepcopy(value)
            continue
        current = merged[key]
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge_dicts(current, value)
            continue
        if current != value:
            raise FinalizeError("parallel_fork_join_merge_conflict")
    return merged


def _merge_jobs(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = {
        "emitted": list(base.get("emitted") or []),
        "submitted": list(base.get("submitted") or []),
    }
    for key in ("emitted", "submitted"):
        seen = set(str(item) for item in merged[key])
        for item in incoming.get(key) or []:
            item_key = str(item)
            if item_key not in seen:
                merged[key].append(item)
                seen.add(item_key)
    return merged


def record_trace(
    state: dict[str, Any],
    *,
    step_id: str,
    primitive_id: str,
    primitive_version: int,
    result: str,
    writes: list[str],
    append_trace: AppendTrace,
) -> dict[str, Any]:
    return append_trace(
        state,
        {
            "step_id": step_id,
            "primitive_id": primitive_id,
            "primitive_version": primitive_version,
            "result": result,
            "writes": writes,
        },
    )


def guard_parallel_map_write_conflicts(
    step: dict[str, Any],
    inputs: dict[str, Any],
) -> None:
    primitive_id = str(step.get("primitive_id") or "")
    primitive_version = int(step.get("primitive_version") or 0)
    if primitive_id != "parallel.map" or primitive_version != 1:
        return
    if inputs.get("merge_mode", "fail_on_conflict") != "fail_on_conflict":
        return
    writes_any = step.get("writes")
    if not isinstance(writes_any, list) or not writes_any:
        return
    write_counts: dict[str, int] = {}
    for write_any in writes_any:
        if not isinstance(write_any, dict):
            continue
        to_path = write_any.get("to_path")
        if not isinstance(to_path, str) or not to_path:
            continue
        write_counts[to_path] = write_counts.get(to_path, 0) + 1
        if write_counts[to_path] > 1:
            raise FinalizeError("parallel_map_conflicting_writes")


def execute_phase2_step(
    *,
    effective_model: dict[str, Any],
    state: dict[str, Any],
    session_id: str,
    step_id: str,
    step: dict[str, Any],
    inputs: dict[str, Any],
    run_graph: RunGraph,
    apply_writes: ApplyWrites,
    append_trace: AppendTrace,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], bool] | None:
    primitive_id = str(step.get("primitive_id") or "")
    primitive_version = int(step.get("primitive_version") or 0)
    if primitive_id == "parallel.fork_join" and primitive_version == 1:
        state, outputs = execute_fork_join(
            effective_model=effective_model,
            state=state,
            session_id=session_id,
            step_id=step_id,
            inputs=inputs,
            run_graph=run_graph,
            append_trace=append_trace,
        )
        return state, outputs, dict(state.get("jobs") or {}), False
    if primitive_id == "flow.invoke" and primitive_version == 1:
        state, outputs = execute_flow_invoke(
            effective_model=effective_model,
            state=state,
            session_id=session_id,
            step_id=step_id,
            inputs=inputs,
            run_graph=run_graph,
        )
        return state, outputs, dict(state.get("jobs") or {}), False
    if primitive_id == "flow.loop" and primitive_version == 1:

        def _invoke_loop_subflow(
            current_state: dict[str, Any],
            parent_step_id: str,
            invoke_inputs: dict[str, Any],
            loop_inputs: dict[str, Any],
        ) -> tuple[dict[str, Any], dict[str, Any]]:
            raw_inputs = dict(step.get("inputs") or {})
            raw_bindings_any = raw_inputs.get("param_bindings")
            resolved_bindings: list[dict[str, Any]] = []
            if isinstance(raw_bindings_any, list):
                for index, binding_any in enumerate(raw_bindings_any):
                    if not isinstance(binding_any, dict):
                        raise FinalizeError("subflow_binding_invalid")
                    name = binding_any.get("name")
                    if not isinstance(name, str) or not name:
                        raise FinalizeError("subflow_binding_invalid")
                    resolved_bindings.append(
                        {
                            "name": name,
                            "value": resolve_phase2_input_value(
                                binding_any.get("value"),
                                state=current_state,
                                inputs=loop_inputs,
                                path=f"$.inputs.param_bindings[{index}].value",
                            ),
                        }
                    )
            return execute_flow_invoke(
                effective_model=effective_model,
                state=current_state,
                session_id=session_id,
                step_id=f"{parent_step_id}.invoke",
                inputs={
                    **invoke_inputs,
                    "param_bindings": resolved_bindings,
                },
                run_graph=run_graph,
            )

        state, outputs = execute_loop(
            state=state,
            step=step,
            inputs=inputs,
            apply_writes=apply_writes,
            append_trace=append_trace,
            invoke_subflow=_invoke_loop_subflow,
        )
        return state, outputs, dict(state.get("jobs") or {}), True
    return None


def execute_fork_join(
    *,
    effective_model: dict[str, Any],
    state: dict[str, Any],
    session_id: str,
    step_id: str,
    inputs: dict[str, Any],
    run_graph: RunGraph,
    append_trace: AppendTrace,
) -> tuple[dict[str, Any], dict[str, Any]]:
    state = ensure_phase2_namespaces(state, "branches")
    branch_order_any = inputs.get("branch_order")
    branches_any = inputs.get("branches")
    if not isinstance(branch_order_any, list) or not isinstance(branches_any, dict):
        raise FinalizeError("parallel_fork_join_invalid")
    base_trace_len = len(list(state.get("trace") or []))
    merged_answers = deepcopy(dict(state.get("answers") or {}))
    merged_vars = deepcopy(dict(state.get("vars") or {}))
    merged_jobs = deepcopy(dict(state.get("jobs") or {}))
    branch_results: dict[str, Any] = {}
    branch_events: list[dict[str, Any]] = []
    for branch_id_any in branch_order_any:
        branch_id = str(branch_id_any)
        spec_any = branches_any.get(branch_id)
        if not isinstance(spec_any, dict):
            raise FinalizeError("parallel_fork_join_invalid")
        branch_state = deepcopy(state)
        branch_inputs = {
            "target_library": spec_any.get("target_library"),
            "target_subflow": spec_any.get("target_subflow"),
            "param_bindings": list(spec_any.get("param_bindings") or []),
        }
        branch_state, outputs = execute_flow_invoke(
            effective_model=effective_model,
            state=branch_state,
            session_id=session_id,
            step_id=f"{step_id}.{branch_id}",
            inputs=branch_inputs,
            run_graph=run_graph,
        )
        branch_results[branch_id] = outputs
        trace_any = branch_state.get("trace")
        trace = list(trace_any) if isinstance(trace_any, list) else []
        branch_events.extend(
            [dict(item) for item in trace[base_trace_len:] if isinstance(item, dict)]
        )
        merged_answers = _merge_dicts(merged_answers, dict(branch_state.get("answers") or {}))
        merged_vars = _merge_dicts(merged_vars, dict(branch_state.get("vars") or {}))
        merged_jobs = _merge_jobs(merged_jobs, dict(branch_state.get("jobs") or {}))
    state["answers"] = merged_answers
    state["vars"] = merged_vars
    state["jobs"] = merged_jobs
    state = ensure_phase2_namespaces(state, "branches")
    branches = dict((state.get("vars") or {}).get("branches") or {})
    branches[step_id] = {
        "branch_order": [str(item) for item in branch_order_any],
        "join_policy": inputs.get("join_policy"),
        "merge_mode": inputs.get("merge_mode"),
        "results": dict(branch_results),
    }
    state["vars"]["branches"] = branches
    for event in branch_events:
        event.pop("seq", None)
        state = append_trace(state, event)
    return state, {
        "branch_order": [str(item) for item in branch_order_any],
        "join_policy": inputs.get("join_policy"),
        "merge_mode": inputs.get("merge_mode"),
        "branch_results": dict(branch_results),
    }


__all__ = [
    "ensure_phase2_namespaces",
    "execute_flow_invoke",
    "execute_fork_join",
    "execute_phase2_step",
    "guard_parallel_map_write_conflicts",
    "record_trace",
    "resolve_phase2_input_value",
    "runtime_input_context",
]
