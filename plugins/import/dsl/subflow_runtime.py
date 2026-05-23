"""Phase II subflow and fork/join runtime helpers for import DSL.

ASCII-only.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Protocol, TypeGuard, cast

from ..errors import FinalizeError
from .expr_eval import eval_expr_ref
from .loop_runtime import execute_loop


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _as_object_list(value: object) -> list[object]:
    return [item for item in value] if _is_object_list(value) else []


def _to_int_or_default(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _state_vars_dict(state: dict[str, object]) -> dict[str, object]:
    vars_map = _as_str_object_dict(state.get("vars"))
    state["vars"] = vars_map
    return vars_map


class RunGraph(Protocol):
    def __call__(
        self,
        graph: dict[str, object],
        state: dict[str, object],
        session_id: str,
    ) -> dict[str, object]: ...


class ApplyWrites(Protocol):
    def __call__(
        self,
        *,
        state: dict[str, object],
        step: dict[str, object],
        inputs: dict[str, object],
        op_outputs: dict[str, object],
    ) -> dict[str, object]: ...


class AppendTrace(Protocol):
    def __call__(self, state: dict[str, object], event: dict[str, object]) -> dict[str, object]: ...


_RESERVED_VAR_NAMESPACES = {"branches", "subflows", "loops"}


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
    path: str,
) -> object:
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
    if _is_str_object_dict(error) and isinstance(error.get("reason"), str):
        reason = str(error.get("reason"))
    raise FinalizeError(reason)


def runtime_input_context(state: dict[str, object]) -> dict[str, object]:
    vars_any = state.get("vars")
    vars_dict = _as_str_object_dict(vars_any)
    subflows = _as_str_object_dict(vars_dict.get("subflows"))
    current = subflows.get("_current_inputs")
    return _as_str_object_dict(current)


def resolve_phase2_input_value(
    value: object,
    *,
    state: dict[str, object],
    inputs: dict[str, object],
    path: str,
) -> object:
    if _is_str_object_dict(value):
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
    if _is_object_list(value):
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
    state: dict[str, object],
    *namespaces: str,
) -> dict[str, object]:
    vars_any = state.get("vars")
    vars_dict = _as_str_object_dict(vars_any)
    targets = namespaces or tuple(sorted(_RESERVED_VAR_NAMESPACES))
    for key in targets:
        if key not in _RESERVED_VAR_NAMESPACES:
            raise FinalizeError("phase2_namespace_invalid")
        current = vars_dict.get(key)
        vars_dict[key] = _as_str_object_dict(current)
    state["vars"] = vars_dict
    return state


def _library_id(
    libraries: dict[str, object],
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


def _bindings_map(bindings_any: object) -> dict[str, object]:
    if not _is_object_list(bindings_any):
        raise FinalizeError("subflow_bindings_invalid")
    out: dict[str, object] = {}
    for item in bindings_any:
        if not _is_str_object_dict(item):
            raise FinalizeError("subflow_bindings_invalid")
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise FinalizeError("subflow_bindings_invalid")
        if name in out:
            raise FinalizeError("subflow_bindings_duplicate")
        out[name] = deepcopy(item.get("value"))
    return out


def _set_current_inputs(
    state: dict[str, object], bindings: dict[str, object]
) -> dict[str, object] | None:
    state = ensure_phase2_namespaces(state, "subflows")
    vars_map = _state_vars_dict(state)
    subflows = _as_str_object_dict(vars_map.get("subflows"))
    previous = subflows.get("_current_inputs")
    previous_dict = _as_str_object_dict(previous) if _is_str_object_dict(previous) else None
    subflows["_current_inputs"] = dict(bindings)
    vars_map["subflows"] = subflows
    state["vars"] = vars_map
    return previous_dict


def _restore_current_inputs(state: dict[str, object], previous: dict[str, object] | None) -> None:
    state = ensure_phase2_namespaces(state, "subflows")
    vars_map = _state_vars_dict(state)
    subflows = _as_str_object_dict(vars_map.get("subflows"))
    if previous is None:
        subflows.pop("_current_inputs", None)
    else:
        subflows["_current_inputs"] = dict(previous)
    vars_map["subflows"] = subflows
    state["vars"] = vars_map


def execute_flow_invoke(
    *,
    effective_model: dict[str, object],
    state: dict[str, object],
    session_id: str,
    step_id: str,
    inputs: dict[str, object],
    run_graph: RunGraph,
) -> tuple[dict[str, object], dict[str, object]]:
    libraries_any = effective_model.get("libraries")
    libraries = _as_str_object_dict(libraries_any)
    target_library = str(inputs.get("target_library") or "")
    target_subflow = str(inputs.get("target_subflow") or "")
    library_id = _library_id(
        libraries,
        target_library=target_library,
        target_subflow=target_subflow,
    )
    library_any = libraries.get(library_id)
    if not _is_str_object_dict(library_any):
        raise FinalizeError("subflow_target_invalid")
    bindings = _bindings_map(inputs.get("param_bindings"))
    state = ensure_phase2_namespaces(state, "subflows")
    saved_status = state.get("status")
    saved_current = str(state.get("current_step_id") or "")
    saved_cursor = _as_str_object_dict(state.get("cursor"))
    previous_inputs = _set_current_inputs(state, bindings)
    state["status"] = "in_progress"
    entry_step_id = str(library_any.get("entry_step_id") or "")
    state["current_step_id"] = entry_step_id
    state["cursor"] = {"step_id": entry_step_id}
    vars_map = _state_vars_dict(state)
    subflows = _as_str_object_dict(vars_map.get("subflows"))
    subflows[step_id] = {
        "target_library": library_id,
        "target_subflow": target_subflow,
        "param_bindings": dict(bindings),
    }
    vars_map["subflows"] = subflows
    state["vars"] = vars_map
    try:
        state = run_graph(dict(library_any), state, session_id)
        return_values = resolve_phase2_input_value(
            _as_str_object_dict(library_any.get("returns")),
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


def _merge_dicts(base: dict[str, object], incoming: dict[str, object]) -> dict[str, object]:
    merged = deepcopy(base)
    for key, value in incoming.items():
        if key in _RESERVED_VAR_NAMESPACES:
            continue
        if key not in merged:
            merged[key] = deepcopy(value)
            continue
        current = merged[key]
        if _is_str_object_dict(current) and _is_str_object_dict(value):
            merged[key] = _merge_dicts(current, value)
            continue
        if current != value:
            raise FinalizeError("parallel_fork_join_merge_conflict")
    return merged


def _merge_jobs(base: dict[str, object], incoming: dict[str, object]) -> dict[str, object]:
    merged_emitted = _as_object_list(base.get("emitted"))
    merged_submitted = _as_object_list(base.get("submitted"))
    merged: dict[str, object] = {
        "emitted": merged_emitted,
        "submitted": merged_submitted,
    }
    for key in ("emitted", "submitted"):
        merged_items = _as_object_list(merged.get(key))
        seen = {str(item) for item in merged_items}
        for item in _as_object_list(incoming.get(key)):
            item_key = str(item)
            if item_key not in seen:
                merged_items.append(item)
                seen.add(item_key)
        merged[key] = merged_items
    return merged


def record_trace(
    state: dict[str, object],
    *,
    step_id: str,
    primitive_id: str,
    primitive_version: int,
    result: str,
    writes: list[str],
    append_trace: AppendTrace,
) -> dict[str, object]:
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
    step: dict[str, object],
    inputs: dict[str, object],
) -> None:
    primitive_id = str(step.get("primitive_id") or "")
    primitive_version = _to_int_or_default(step.get("primitive_version"), 0)
    if primitive_id != "parallel.map" or primitive_version != 1:
        return
    if inputs.get("merge_mode", "fail_on_conflict") != "fail_on_conflict":
        return
    writes_any = step.get("writes")
    if not _is_object_list(writes_any) or not writes_any:
        return
    write_counts: dict[str, int] = {}
    for write_any in writes_any:
        if not _is_str_object_dict(write_any):
            continue
        to_path = write_any.get("to_path")
        if not isinstance(to_path, str) or not to_path:
            continue
        write_counts[to_path] = write_counts.get(to_path, 0) + 1
        if write_counts[to_path] > 1:
            raise FinalizeError("parallel_map_conflicting_writes")


def execute_phase2_step(
    *,
    effective_model: dict[str, object],
    state: dict[str, object],
    session_id: str,
    step_id: str,
    step: dict[str, object],
    inputs: dict[str, object],
    run_graph: RunGraph,
    apply_writes: ApplyWrites,
    append_trace: AppendTrace,
) -> tuple[dict[str, object], dict[str, object], dict[str, object], bool] | None:
    primitive_id = str(step.get("primitive_id") or "")
    primitive_version = _to_int_or_default(step.get("primitive_version"), 0)
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
        return state, outputs, _as_str_object_dict(state.get("jobs")), False
    if primitive_id == "flow.invoke" and primitive_version == 1:
        state, outputs = execute_flow_invoke(
            effective_model=effective_model,
            state=state,
            session_id=session_id,
            step_id=step_id,
            inputs=inputs,
            run_graph=run_graph,
        )
        return state, outputs, _as_str_object_dict(state.get("jobs")), False
    if primitive_id == "flow.loop" and primitive_version == 1:

        def _invoke_loop_subflow(
            state: dict[str, object],
            step_id: str,
            invoke_inputs: dict[str, object],
            loop_inputs: dict[str, object],
        ) -> tuple[dict[str, object], dict[str, object]]:
            raw_inputs = _as_str_object_dict(step.get("inputs"))
            raw_bindings_any = raw_inputs.get("param_bindings")
            resolved_bindings: list[dict[str, object]] = []
            if _is_object_list(raw_bindings_any):
                for index, binding_any in enumerate(raw_bindings_any):
                    if not _is_str_object_dict(binding_any):
                        raise FinalizeError("subflow_binding_invalid")
                    name = binding_any.get("name")
                    if not isinstance(name, str) or not name:
                        raise FinalizeError("subflow_binding_invalid")
                    resolved_bindings.append(
                        {
                            "name": name,
                            "value": resolve_phase2_input_value(
                                binding_any.get("value"),
                                state=state,
                                inputs=loop_inputs,
                                path=f"$.inputs.param_bindings[{index}].value",
                            ),
                        }
                    )
            return execute_flow_invoke(
                effective_model=effective_model,
                state=state,
                session_id=session_id,
                step_id=f"{step_id}.invoke",
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
        return state, outputs, _as_str_object_dict(state.get("jobs")), True
    return None


def execute_fork_join(
    *,
    effective_model: dict[str, object],
    state: dict[str, object],
    session_id: str,
    step_id: str,
    inputs: dict[str, object],
    run_graph: RunGraph,
    append_trace: AppendTrace,
) -> tuple[dict[str, object], dict[str, object]]:
    state = ensure_phase2_namespaces(state, "branches")
    branch_order_any = inputs.get("branch_order")
    branches_any = inputs.get("branches")
    if not _is_object_list(branch_order_any) or not _is_str_object_dict(branches_any):
        raise FinalizeError("parallel_fork_join_invalid")
    base_trace_len = len(_as_object_list(state.get("trace")))
    merged_answers = deepcopy(_as_str_object_dict(state.get("answers")))
    merged_vars = deepcopy(_as_str_object_dict(state.get("vars")))
    merged_jobs = deepcopy(_as_str_object_dict(state.get("jobs")))
    branch_results: dict[str, object] = {}
    branch_events: list[dict[str, object]] = []
    for branch_id_any in branch_order_any:
        branch_id = str(branch_id_any)
        spec_any = branches_any.get(branch_id)
        if not _is_str_object_dict(spec_any):
            raise FinalizeError("parallel_fork_join_invalid")
        branch_state = deepcopy(state)
        branch_inputs = {
            "target_library": spec_any.get("target_library"),
            "target_subflow": spec_any.get("target_subflow"),
            "param_bindings": _as_object_list(spec_any.get("param_bindings")),
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
        trace = _as_object_list(trace_any)
        branch_events.extend(
            [dict(item) for item in trace[base_trace_len:] if _is_str_object_dict(item)]
        )
        merged_answers = _merge_dicts(
            merged_answers,
            _as_str_object_dict(branch_state.get("answers")),
        )
        merged_vars = _merge_dicts(
            merged_vars,
            _as_str_object_dict(branch_state.get("vars")),
        )
        merged_jobs = _merge_jobs(
            merged_jobs,
            _as_str_object_dict(branch_state.get("jobs")),
        )
    state["answers"] = merged_answers
    state["vars"] = merged_vars
    state["jobs"] = merged_jobs
    state = ensure_phase2_namespaces(state, "branches")
    vars_map = _state_vars_dict(state)
    branches = _as_str_object_dict(vars_map.get("branches"))
    branches[step_id] = {
        "branch_order": [str(item) for item in branch_order_any],
        "join_policy": inputs.get("join_policy"),
        "merge_mode": inputs.get("merge_mode"),
        "results": dict(branch_results),
    }
    vars_map["branches"] = branches
    state["vars"] = vars_map
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
