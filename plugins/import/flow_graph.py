"""FlowGraph normalization and next-step selection for wizard execution.

FlowGraph is a deterministic directed graph of step transitions.

The engine uses FlowGraph to select the next step after a submit.
Renderers remain neutral.

ASCII-only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeGuard

from .conditions import eval_condition, find_invalid_condition_path
from .errors import FinalizeError

MAX_TRANSITION_HOPS = 50


@dataclass(frozen=True, slots=True)
class FlowEdge:
    from_step_id: str
    to_step_id: str
    when: Any | None = None
    priority: int = 0


@dataclass(frozen=True, slots=True)
class FlowGraph:
    version: int
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
        prio = 0
        for a, b in zip(nodes_v1, nodes_v1[1:], strict=False):
            edges_v1.append(FlowEdge(from_step_id=a, to_step_id=b, when=None, priority=prio))
            prio += 10

        g = FlowGraph(
            version=1,
            entry_step_id=entry,
            nodes=tuple(nodes_v1),
            edges=tuple(edges_v1),
        )
        g = _inject_conflict_rules(g)
        _validate_graph(g)
        return g

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

            if "priority" not in e:
                raise FinalizeError("MISSING_PRIORITY: " + frm + "->" + to)
            prio_any = e.get("priority")
            if not _is_strict_int(prio_any):
                raise FinalizeError(
                    "AMBIGUOUS_TRANSITION: invalid_priority_type " + frm + "->" + to
                )
            edges_v2.append(
                FlowEdge(
                    from_step_id=frm,
                    to_step_id=to,
                    when=e.get("when"),
                    priority=prio_any,
                )
            )

        g = FlowGraph(
            version=2,
            entry_step_id=entry,
            nodes=tuple(nodes_v2),
            edges=tuple(edges_v2),
        )
        g = _inject_conflict_rules(g)
        _validate_graph(g)
        return g

    raise FinalizeError("wizard_definition version must be 1 or 2")


def select_next_step(
    graph: FlowGraph,
    *,
    current_step_id: str,
    state_view: dict[str, Any],
    is_step_enabled: Callable[[str], bool],
    debug_log: Callable[[str, dict[str, Any]], None] | None = None,
) -> str:
    if current_step_id not in graph.nodes:
        raise FinalizeError(f"unknown current_step_id: {current_step_id}")

    edges = tuple(sorted(graph.outgoing(current_step_id), key=lambda e: e.priority))

    evaluated_edges: list[dict[str, Any]] = []
    matched_edges: list[FlowEdge] = []

    def _warn(kind: str, payload: dict[str, Any]) -> None:
        if debug_log is None:
            return
        debug_log(kind, dict(payload))

    for e in edges:
        matched = eval_condition(e.when, state_view, warn=_warn)
        if matched:
            matched_edges.append(e)
        evaluated_edges.append(
            {
                "to": e.to_step_id,
                "when": _summarize_when(e.when),
                "matched": bool(matched),
                "enabled_target": bool(is_step_enabled(e.to_step_id)),
                "priority": e.priority,
            }
        )

    if len(matched_edges) >= 2:
        raise FinalizeError(
            "AMBIGUOUS_TRANSITION: "
            + current_step_id
            + " matches="
            + str([{"to": e.to_step_id, "priority": e.priority} for e in matched_edges])
        )

    def _resolve_enabled_target(start: str) -> str | None:
        visited: list[str] = []
        seen: set[str] = set()
        cur = start
        while True:
            if cur in seen:
                raise FinalizeError("CYCLE_DETECTED: " + ",".join(visited + [cur]))
            seen.add(cur)
            visited.append(cur)
            if is_step_enabled(cur):
                return cur

            try:
                idx = graph.nodes.index(cur)
            except ValueError:
                return None
            nxt = None
            for sid in graph.nodes[idx + 1 :]:
                if sid not in seen:
                    nxt = sid
                    break
            if nxt is None:
                return None
            cur = nxt

    if len(matched_edges) == 0:
        raise FinalizeError(
            "NO_TRANSITION: " + current_step_id + " edges=" + str(len(evaluated_edges))
        )

    target = _resolve_enabled_target(matched_edges[0].to_step_id)
    if target is not None:
        return target
    raise FinalizeError("NO_TRANSITION: " + current_step_id + " target_disabled")


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
                priority=0,
            )
        )

    # 1) Not confirmed -> stay
    edges.append(
        FlowEdge(
            from_step_id="final_summary_confirm",
            to_step_id="final_summary_confirm",
            when={
                "op": "ne",
                "path": "$.inputs.final_summary_confirm.confirm_start",
                "value": True,
            },
            priority=0,
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
                        "path": "$.inputs.final_summary_confirm.confirm_start",
                        "value": True,
                    },
                    {
                        "op": "ne",
                        "path": "$.state.conflicts.policy",
                        "value": "ask",
                    },
                ],
            },
            priority=10,
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
                            "path": "$.inputs.final_summary_confirm.confirm_start",
                            "value": True,
                        },
                        {
                            "op": "eq",
                            "path": "$.state.conflicts.policy",
                            "value": "ask",
                        },
                        {
                            "op": "eq",
                            "path": "$.state.conflicts.present",
                            "value": True,
                        },
                        {
                            "op": "eq",
                            "path": "$.state.conflicts.resolved",
                            "value": False,
                        },
                    ],
                },
                priority=20,
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
                        "path": "$.inputs.final_summary_confirm.confirm_start",
                        "value": True,
                    },
                    {
                        "op": "eq",
                        "path": "$.state.conflicts.policy",
                        "value": "ask",
                    },
                    {
                        "op": "or",
                        "conds": [
                            {
                                "op": "ne",
                                "path": "$.state.conflicts.present",
                                "value": True,
                            },
                            {
                                "op": "ne",
                                "path": "$.state.conflicts.resolved",
                                "value": False,
                            },
                        ],
                    },
                ],
            },
            priority=30,
        )
    )

    return FlowGraph(
        version=graph.version,
        entry_step_id=graph.entry_step_id,
        nodes=graph.nodes,
        edges=tuple(edges),
    )


_CONFLICT_FROM_IDS: set[str] = {"final_summary_confirm", "resolve_conflicts_batch"}


def _summarize_when(when: Any | None) -> str:
    if when is None:
        return "<unconditional>"
    if isinstance(when, bool):
        return "true" if when else "false"
    if isinstance(when, dict):
        op = when.get("op")
        if isinstance(op, str) and op:
            path = when.get("path")
            if isinstance(path, str) and path:
                return f"{op}:{path}"
            return op
    return "<cond>"


def _validate_graph(graph: FlowGraph) -> None:
    outgoing: dict[str, list[FlowEdge]] = {n: [] for n in graph.nodes}
    for e in graph.edges:
        outgoing.setdefault(e.from_step_id, []).append(e)

    for frm, edges in outgoing.items():
        seen_priorities: set[int] = set()
        for e in edges:
            if e.priority in seen_priorities:
                raise FinalizeError(
                    "AMBIGUOUS_TRANSITION: duplicate_priority "
                    + frm
                    + " priority="
                    + str(e.priority)
                )
            seen_priorities.add(e.priority)

        unconditional = [e for e in edges if e.when is None]
        if len(unconditional) > 1:
            raise FinalizeError(
                "AMBIGUOUS_TRANSITION: " + frm + " edges=" + str(len(unconditional))
            )

        for e in edges:
            bad = find_invalid_condition_path(e.when)
            if bad is not None:
                raise FinalizeError(
                    "INVALID_CONDITION_PATH: " + bad + " " + e.from_step_id + "->" + e.to_step_id
                )


def _is_strict_int(v: Any) -> TypeGuard[int]:
    return isinstance(v, int) and not isinstance(v, bool)
