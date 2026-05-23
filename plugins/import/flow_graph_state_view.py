"""Shared FlowGraph state-view authority for import branching.

ASCII-only.
"""

from __future__ import annotations

from typing import TypedDict, TypeGuard, cast

FlowGraphInputs = dict[str, object]
FlowGraphConflicts = dict[str, object]


class FlowGraphRuntimeState(TypedDict):
    conflicts: FlowGraphConflicts
    phase: object | None
    current_step_id: object | None


class FlowGraphStateView(TypedDict):
    inputs: FlowGraphInputs
    state: FlowGraphRuntimeState


def _dict_view(raw: object) -> dict[str, object]:
    if _is_str_object_dict(raw):
        return dict(raw)
    return {}


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def build_flow_graph_state_view(state: dict[str, object]) -> FlowGraphStateView:
    return {
        "inputs": _dict_view(state.get("inputs")),
        "state": {
            "conflicts": _dict_view(state.get("conflicts")),
            "phase": state.get("phase"),
            "current_step_id": state.get("current_step_id"),
        },
    }
