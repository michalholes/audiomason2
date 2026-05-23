"""Phase II loop runtime helpers for import DSL.

ASCII-only.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Protocol, TypeGuard, cast

from ..errors import FinalizeError


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


class InvokeLoopSubflow(Protocol):
    def __call__(
        self,
        state: dict[str, object],
        step_id: str,
        invoke_inputs: dict[str, object],
        loop_inputs: dict[str, object],
    ) -> tuple[dict[str, object], dict[str, object]]: ...


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _to_int_or_default(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _ensure_loop_namespace(state: dict[str, object]) -> dict[str, object]:
    vars_any = state.get("vars")
    vars_dict = _as_str_object_dict(vars_any)
    loops_any = vars_dict.get("loops")
    vars_dict["loops"] = _as_str_object_dict(loops_any)
    state["vars"] = vars_dict
    return state


def execute_loop(
    *,
    state: dict[str, object],
    step: dict[str, object],
    inputs: dict[str, object],
    apply_writes: ApplyWrites,
    append_trace: AppendTrace,
    invoke_subflow: InvokeLoopSubflow | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    iterable = inputs.get("iterable_expr")
    item_var = str(inputs.get("item_var") or "")
    max_iterations = inputs.get("max_iterations")
    if not _is_object_list(iterable):
        raise FinalizeError("loop_iterable_invalid")
    max_iterations_int = _to_int_or_default(max_iterations, 0)
    if max_iterations_int < 1:
        raise FinalizeError("loop_max_iterations_invalid")
    if len(iterable) > max_iterations_int:
        raise FinalizeError("loop_max_iterations_exceeded")

    step_id = str(step.get("step_id") or "")
    primitive_id = str(step.get("primitive_id") or "")
    primitive_version = _to_int_or_default(step.get("primitive_version"), 0)
    writes_any = step.get("writes")
    writes = (
        [str(item.get("to_path") or "") for item in writes_any if _is_str_object_dict(item)]
        if _is_object_list(writes_any)
        else []
    )

    state = _ensure_loop_namespace(state)
    history: list[dict[str, object]] = []
    results: list[dict[str, object]] = []
    target_library = inputs.get("target_library")
    target_subflow = inputs.get("target_subflow")
    param_bindings_any = inputs.get("param_bindings")
    invoke_enabled = (
        isinstance(target_library, str)
        and bool(target_library)
        and isinstance(target_subflow, str)
        and bool(target_subflow)
        and _is_object_list(param_bindings_any)
    )
    if invoke_enabled and invoke_subflow is None:
        raise FinalizeError("loop_subflow_invoke_missing")
    for iteration_index, item in enumerate(iterable):
        state = _ensure_loop_namespace(state)
        vars_map = _as_str_object_dict(state.get("vars"))
        loops = _as_str_object_dict(vars_map.get("loops"))
        loop_inputs = dict(inputs)
        loop_inputs[item_var] = deepcopy(item)
        loop_inputs["iteration_index"] = iteration_index
        history.append({"iteration_index": iteration_index, "item": deepcopy(item)})
        loops[step_id] = {
            "item_var": item_var,
            "iteration_index": iteration_index,
            "max_iterations": max_iterations_int,
            "history": deepcopy(history),
        }
        vars_map["loops"] = loops
        state["vars"] = vars_map
        iteration_outputs = {
            "item": deepcopy(item),
            "iteration_index": iteration_index,
        }
        if invoke_enabled:
            invoke_inputs = {
                "target_library": target_library,
                "target_subflow": target_subflow,
                "param_bindings": deepcopy(param_bindings_any) if invoke_enabled else [],
            }
            if invoke_subflow is None:
                raise RuntimeError("loop_subflow_invoker_missing")
            state, subflow_outputs = invoke_subflow(state, step_id, invoke_inputs, loop_inputs)
            iteration_outputs["subflow"] = deepcopy(subflow_outputs)
            results.append(
                {
                    "iteration_index": iteration_index,
                    "item": deepcopy(item),
                    "subflow": deepcopy(subflow_outputs),
                }
            )
        iteration_outputs["results"] = deepcopy(results)
        state = apply_writes(
            state=state,
            step=step,
            inputs=loop_inputs,
            op_outputs=iteration_outputs,
        )
        state = append_trace(
            state,
            {
                "step_id": step_id,
                "primitive_id": primitive_id,
                "primitive_version": primitive_version,
                "result": "OK",
                "writes": list(writes),
                "iteration_index": iteration_index,
            },
        )
    state = _ensure_loop_namespace(state)
    vars_map = _as_str_object_dict(state.get("vars"))
    loops = _as_str_object_dict(vars_map.get("loops"))
    loops[step_id] = {
        "item_var": item_var,
        "completed_iterations": len(iterable),
        "max_iterations": max_iterations_int,
        "history": history,
    }
    vars_map["loops"] = loops
    state["vars"] = vars_map
    return state, {
        "items": list(iterable),
        "completed_iterations": len(iterable),
        "results": results,
    }


__all__ = ["execute_loop"]
