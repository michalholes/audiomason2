"""FlowModel builder and helpers for WizardDefinition v3.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from ..errors import FinalizeError
from ..primitives.ui_v1 import project_prompt_ui

FLOWMODEL_KIND = "dsl_step_graph_v3"
FLOW_ID = "import_v3"


def build_flow_model_v3(*, wizard_definition: dict[str, Any]) -> dict[str, Any]:
    if wizard_definition.get("version") != 3:
        raise FinalizeError("wizard_definition must be version 3")

    entry_step_id = wizard_definition.get("entry_step_id")
    if not isinstance(entry_step_id, str) or not entry_step_id:
        raise FinalizeError("wizard_definition entry_step_id must be a string")

    nodes_any = wizard_definition.get("nodes")
    if not isinstance(nodes_any, list) or not nodes_any:
        raise FinalizeError("wizard_definition nodes must be a non-empty list")

    edges_any = wizard_definition.get("edges")
    if not isinstance(edges_any, list):
        raise FinalizeError("wizard_definition edges must be a list")

    steps: list[dict[str, Any]] = []
    seen: set[str] = set()
    for node_any in nodes_any:
        if not isinstance(node_any, dict):
            raise FinalizeError("wizard_definition node must be an object")
        step_id = node_any.get("step_id")
        op_any = node_any.get("op")
        if not isinstance(step_id, str) or not step_id:
            raise FinalizeError("wizard_definition node step_id must be a string")
        if not isinstance(op_any, dict):
            raise FinalizeError("wizard_definition node op must be an object")
        primitive_id = op_any.get("primitive_id")
        primitive_version = op_any.get("primitive_version")
        if not isinstance(primitive_id, str) or not primitive_id:
            raise FinalizeError("wizard_definition primitive_id must be a string")
        if not isinstance(primitive_version, int):
            raise FinalizeError("wizard_definition primitive_version must be int")
        if step_id in seen:
            raise FinalizeError("wizard_definition step_id must be unique")
        seen.add(step_id)
        inputs_any = op_any.get("inputs")
        writes_any = op_any.get("writes")
        step: dict[str, Any] = {
            "step_id": step_id,
            "phase": 1,
            "title": step_id,
            "primitive_id": primitive_id,
            "primitive_version": primitive_version,
            "inputs": dict(inputs_any) if isinstance(inputs_any, dict) else {},
            "writes": list(writes_any) if isinstance(writes_any, list) else [],
        }
        try:
            ui = project_prompt_ui(
                primitive_id,
                primitive_version,
                step["inputs"],
            )
        except ValueError as exc:
            raise FinalizeError(str(exc)) from exc
        if ui:
            step["ui"] = ui
        steps.append(step)

    if entry_step_id not in seen:
        raise FinalizeError("wizard_definition entry_step_id must exist in nodes")

    edges: list[dict[str, Any]] = []
    for edge_any in edges_any:
        if not isinstance(edge_any, dict):
            raise FinalizeError("wizard_definition edge must be an object")
        frm = edge_any.get("from")
        to = edge_any.get("to")
        if not isinstance(frm, str) or frm not in seen:
            raise FinalizeError("wizard_definition edge.from must reference known step_id")
        if not isinstance(to, str) or to not in seen:
            raise FinalizeError("wizard_definition edge.to must reference known step_id")
        edge = {"from": frm, "to": to}
        cond = edge_any.get("condition_expr")
        if cond is not None:
            edge["condition_expr"] = cond
        edges.append(edge)

    return {
        "flow_id": FLOW_ID,
        "flowmodel_kind": FLOWMODEL_KIND,
        "entry_step_id": entry_step_id,
        "steps": steps,
        "edges": sorted(
            edges,
            key=lambda item: (
                str(item.get("from") or ""),
                str(item.get("to") or ""),
                str((item.get("condition_expr") or {}).get("expr") or ""),
            ),
        ),
    }


def step_map(effective_model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    steps_any = effective_model.get("steps")
    if not isinstance(steps_any, list):
        raise FinalizeError("effective_model steps must be a list")
    out: dict[str, dict[str, Any]] = {}
    for step_any in steps_any:
        if not isinstance(step_any, dict):
            continue
        step_id = step_any.get("step_id")
        if isinstance(step_id, str) and step_id:
            out[step_id] = dict(step_any)
    return out


def get_step(effective_model: dict[str, Any], step_id: str) -> dict[str, Any]:
    steps = step_map(effective_model)
    if step_id not in steps:
        raise FinalizeError("unknown step_id")
    return steps[step_id]


__all__ = ["FLOWMODEL_KIND", "build_flow_model_v3", "get_step", "step_map"]
