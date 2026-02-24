"""FlowGraph normalization and next-step selection for wizard execution.

FlowGraph is a deterministic directed graph of step transitions.

The engine uses FlowGraph to select the next step after a submit.
Renderers remain neutral.

ASCII-only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .conditions import eval_condition
from .errors import FinalizeError


@dataclass(frozen=True, slots=True)
class FlowEdge:
    from_step_id: str
    to_step_id: str
    when: Any | None = None


@dataclass(frozen=True, slots=True)
class FlowGraph:
    entry_step_id: str
    nodes: tuple[str, ...]
    edges: tuple[FlowEdge, ...]

    def outgoing(self, step_id: str) -> tuple[FlowEdge, ...]:
        return tuple(e for e in self.edges if e.from_step_id == step_id)


def normalize_to_graph(
    wizard_definition: dict[str, Any],
    *,
    known_step_ids: set[str],
) -> FlowGraph:
    """Normalize WizardDefinition v1/v2 into a FlowGraph.

    v1 input:
      {"version": 1, "wizard_id": "import", "steps": [{"step_id": "..."}...]}

    v2 input:
      {"version": 2, "wizard_id": "import", "graph": {...}}

    For v1, the returned graph is linear. Conflict semantics (spec 10.3.4)
    are enforced by injecting conditional edges for the conflict steps.
    """
    version_any = wizard_definition.get("version")
    version = int(version_any) if isinstance(version_any, int) else 1

    if version == 1:
        steps_any = wizard_definition.get("steps")
        if not isinstance(steps_any, list) or not steps_any:
            raise FinalizeError("wizard_definition steps must be a non-empty list")

        nodes_v1: list[str] = []
        for s in steps_any:
            sid = s.get("step_id") if isinstance(s, dict) else None
            if not isinstance(sid, str) or not sid:
                raise FinalizeError("wizard_definition contains invalid step_id")
            if sid not in known_step_ids:
                raise FinalizeError(f"wizard_definition contains unknown step_id: {sid}")
            nodes_v1.append(sid)

        entry = nodes_v1[0]
        edges_v1: list[FlowEdge] = []
        for a, b in zip(nodes_v1, nodes_v1[1:], strict=False):
            edges_v1.append(FlowEdge(from_step_id=a, to_step_id=b, when=None))

        g = FlowGraph(entry_step_id=entry, nodes=tuple(nodes_v1), edges=tuple(edges_v1))
        return _inject_conflict_rules(g)

    if version == 2:
        graph_any = wizard_definition.get("graph")
        if not isinstance(graph_any, dict):
            raise FinalizeError("wizard_definition graph must be an object")

        entry_any = graph_any.get("entry_step_id")
        if not isinstance(entry_any, str) or not entry_any:
            raise FinalizeError("wizard_definition graph entry_step_id must be a string")
        entry = entry_any

        nodes_any = graph_any.get("nodes")
        if not isinstance(nodes_any, list) or not nodes_any:
            raise FinalizeError("wizard_definition graph nodes must be a non-empty list")

        nodes_v2: list[str] = []
        seen: set[str] = set()
        for n in nodes_any:
            sid = n.get("step_id") if isinstance(n, dict) else None
            if not isinstance(sid, str) or not sid:
                raise FinalizeError("wizard_definition graph nodes must contain step_id strings")
            if sid in seen:
                raise FinalizeError("wizard_definition graph node step_id must be unique")
            if sid not in known_step_ids:
                raise FinalizeError(f"wizard_definition contains unknown step_id: {sid}")
            seen.add(sid)
            nodes_v2.append(sid)

        if entry not in seen:
            raise FinalizeError("wizard_definition graph entry_step_id must exist in nodes")

        edges_any = graph_any.get("edges")
        if not isinstance(edges_any, list):
            raise FinalizeError("wizard_definition graph edges must be a list")

        edges_v2: list[FlowEdge] = []
        for e in edges_any:
            if not isinstance(e, dict):
                raise FinalizeError("wizard_definition graph edges must be objects")
            frm = e.get("from_step_id")
            to = e.get("to_step_id")
            if not isinstance(frm, str) or not frm:
                raise FinalizeError("wizard_definition graph edges require from_step_id")
            if not isinstance(to, str) or not to:
                raise FinalizeError("wizard_definition graph edges require to_step_id")
            if frm not in seen:
                raise FinalizeError("wizard_definition graph edge references unknown from_step_id")
            if to not in seen:
                raise FinalizeError("wizard_definition graph edge references unknown to_step_id")
            edges_v2.append(FlowEdge(from_step_id=frm, to_step_id=to, when=e.get("when")))

        g = FlowGraph(entry_step_id=entry, nodes=tuple(nodes_v2), edges=tuple(edges_v2))
        return _inject_conflict_rules(g)

    raise FinalizeError("wizard_definition version must be 1 or 2")


def select_next_step(
    graph: FlowGraph,
    *,
    current_step_id: str,
    state_view: dict[str, Any],
    is_step_enabled: Callable[[str], bool],
) -> str:
    if current_step_id not in graph.nodes:
        raise FinalizeError(f"unknown current_step_id: {current_step_id}")

    edges = graph.outgoing(current_step_id)
    for e in edges:
        if not eval_condition(e.when, state_view):
            continue
        if not is_step_enabled(e.to_step_id):
            continue
        return e.to_step_id

    # Fallback for v2 graphs that omit explicit edges for linear transitions:
    # use nodes ordering to pick the next enabled step deterministically.
    try:
        idx = graph.nodes.index(current_step_id)
    except ValueError:
        idx = -1
    if idx >= 0:
        for sid in graph.nodes[idx + 1 :]:
            if is_step_enabled(sid):
                return sid

    raise FinalizeError(f"no valid transition from step_id: {current_step_id}")


def _inject_conflict_rules(graph: FlowGraph) -> FlowGraph:
    """Enforce spec 10.3.4 conflict rules.

    This function removes any existing outgoing edges from:
    - final_summary_confirm
    - resolve_conflicts_batch

    and replaces them with the canonical conditional rules.

    This keeps v1 (linear) graphs compatible with conflict branching.
    """
    if "final_summary_confirm" not in graph.nodes or "processing" not in graph.nodes:
        return graph

    edges = [e for e in graph.edges if e.from_step_id not in _CONFLICT_FROM_IDS]

    if "resolve_conflicts_batch" in graph.nodes:
        edges.append(
            FlowEdge(
                from_step_id="resolve_conflicts_batch",
                to_step_id="final_summary_confirm",
                when=None,
            )
        )

    # 1) Not confirmed -> stay
    edges.append(
        FlowEdge(
            from_step_id="final_summary_confirm",
            to_step_id="final_summary_confirm",
            when={
                "op": "ne",
                "path": "inputs.final_summary_confirm.confirm_start",
                "value": True,
            },
        )
    )

    # 2) policy != ask -> processing
    edges.append(
        FlowEdge(
            from_step_id="final_summary_confirm",
            to_step_id="processing",
            when={
                "op": "and",
                "conds": [
                    {
                        "op": "eq",
                        "path": "inputs.final_summary_confirm.confirm_start",
                        "value": True,
                    },
                    {
                        "op": "ne",
                        "path": "state.conflicts.policy",
                        "value": "ask",
                    },
                ],
            },
        )
    )

    # 3) ask + conflicts -> resolve
    if "resolve_conflicts_batch" in graph.nodes:
        edges.append(
            FlowEdge(
                from_step_id="final_summary_confirm",
                to_step_id="resolve_conflicts_batch",
                when={
                    "op": "and",
                    "conds": [
                        {
                            "op": "eq",
                            "path": "inputs.final_summary_confirm.confirm_start",
                            "value": True,
                        },
                        {
                            "op": "eq",
                            "path": "state.conflicts.policy",
                            "value": "ask",
                        },
                        {
                            "op": "eq",
                            "path": "state.conflicts.present",
                            "value": True,
                        },
                        {
                            "op": "eq",
                            "path": "state.conflicts.resolved",
                            "value": False,
                        },
                    ],
                },
            )
        )

    # 4) ask + no conflicts -> processing
    edges.append(
        FlowEdge(
            from_step_id="final_summary_confirm",
            to_step_id="processing",
            when={
                "op": "and",
                "conds": [
                    {
                        "op": "eq",
                        "path": "inputs.final_summary_confirm.confirm_start",
                        "value": True,
                    },
                    {
                        "op": "eq",
                        "path": "state.conflicts.policy",
                        "value": "ask",
                    },
                    {
                        "op": "or",
                        "conds": [
                            {
                                "op": "ne",
                                "path": "state.conflicts.present",
                                "value": True,
                            },
                            {
                                "op": "ne",
                                "path": "state.conflicts.resolved",
                                "value": False,
                            },
                        ],
                    },
                ],
            },
        )
    )

    return FlowGraph(entry_step_id=graph.entry_step_id, nodes=graph.nodes, edges=tuple(edges))


_CONFLICT_FROM_IDS: set[str] = {"final_summary_confirm", "resolve_conflicts_batch"}
