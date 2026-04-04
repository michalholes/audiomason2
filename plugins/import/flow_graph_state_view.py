"""Shared FlowGraph state-view authority for import branching.

ASCII-only.
"""

from __future__ import annotations

from typing import Any, TypedDict

FlowGraphInputs = dict[str, Any]
FlowGraphConflicts = dict[str, Any]


class FlowGraphRuntimeState(TypedDict):
    conflicts: FlowGraphConflicts
    phase: object | None
    current_step_id: object | None


class FlowGraphStateView(TypedDict):
    inputs: FlowGraphInputs
    state: FlowGraphRuntimeState


def _dict_view(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    return {}


def build_flow_graph_state_view(state: dict[str, Any]) -> FlowGraphStateView:
    return {
        "inputs": _dict_view(state.get("inputs")),
        "state": {
            "conflicts": _dict_view(state.get("conflicts")),
            "phase": state.get("phase"),
            "current_step_id": state.get("current_step_id"),
        },
    }
