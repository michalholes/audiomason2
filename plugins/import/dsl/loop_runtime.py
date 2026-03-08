"""Phase II loop runtime helpers for import DSL.

ASCII-only.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from ..errors import FinalizeError

ApplyWrites = Callable[..., dict[str, Any]]
AppendTrace = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


def _ensure_loop_namespace(state: dict[str, Any]) -> dict[str, Any]:
    vars_any = state.get("vars")
    vars_dict = dict(vars_any) if isinstance(vars_any, dict) else {}
    loops_any = vars_dict.get("loops")
    vars_dict["loops"] = dict(loops_any) if isinstance(loops_any, dict) else {}
    state["vars"] = vars_dict
    return state


def execute_loop(
    *,
    state: dict[str, Any],
    step: dict[str, Any],
    inputs: dict[str, Any],
    apply_writes: ApplyWrites,
    append_trace: AppendTrace,
) -> tuple[dict[str, Any], dict[str, Any]]:
    iterable = inputs.get("iterable_expr")
    item_var = str(inputs.get("item_var") or "")
    max_iterations = inputs.get("max_iterations")
    if not isinstance(iterable, list):
        raise FinalizeError("loop_iterable_invalid")
    if not isinstance(max_iterations, int) or max_iterations < 1:
        raise FinalizeError("loop_max_iterations_invalid")
    if len(iterable) > max_iterations:
        raise FinalizeError("loop_max_iterations_exceeded")

    step_id = str(step.get("step_id") or "")
    primitive_id = str(step.get("primitive_id") or "")
    primitive_version = int(step.get("primitive_version") or 0)
    writes_any = step.get("writes")
    writes = (
        [str(item.get("to_path")) for item in writes_any if isinstance(item, dict)]
        if isinstance(writes_any, list)
        else []
    )

    state = _ensure_loop_namespace(state)
    loops = dict((state.get("vars") or {}).get("loops") or {})
    history: list[dict[str, Any]] = []
    for iteration_index, item in enumerate(iterable):
        loop_inputs = dict(inputs)
        loop_inputs[item_var] = deepcopy(item)
        loop_inputs["iteration_index"] = iteration_index
        history.append({"iteration_index": iteration_index, "item": deepcopy(item)})
        loops[step_id] = {
            "item_var": item_var,
            "iteration_index": iteration_index,
            "max_iterations": max_iterations,
            "history": deepcopy(history),
        }
        state["vars"]["loops"] = loops
        state = apply_writes(
            state=state,
            step=step,
            inputs=loop_inputs,
            op_outputs={
                "item": deepcopy(item),
                "iteration_index": iteration_index,
            },
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
    loops[step_id] = {
        "item_var": item_var,
        "completed_iterations": len(iterable),
        "max_iterations": max_iterations,
        "history": history,
    }
    state["vars"]["loops"] = loops
    return state, {"items": list(iterable), "completed_iterations": len(iterable)}


__all__ = ["execute_loop"]
