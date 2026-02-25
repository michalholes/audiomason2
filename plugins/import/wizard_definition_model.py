"""WizardDefinition model for the import wizard.

This module defines the default workflow ordering as data (Python-defined),
bootstraps a runtime JSON artifact under the wizards root if missing, and
produces an effective step ordering for session creation.

No repo JSON is authoritative.

ASCII-only.
"""

from __future__ import annotations

from typing import Any, TypeGuard

from plugins.file_io.service import FileService
from plugins.file_io.service.types import RootName

from .conditions import find_invalid_condition_path
from .errors import FinalizeError
from .flow_runtime import CANONICAL_STEP_ORDER, MANDATORY_STEP_IDS, OPTIONAL_STEP_IDS
from .step_catalog import STEP_CATALOG
from .storage import atomic_write_json_if_missing, read_json

WIZARD_DEFINITION_REL_PATH = "import/definitions/wizard_definition.json"

# The default workflow definition is Python-defined and is used only for
# bootstrap if the runtime artifact is missing.
DEFAULT_WIZARD_DEFINITION: dict[str, Any] = {
    "version": 1,
    "wizard_id": "import",
    "steps": [{"step_id": sid} for sid in CANONICAL_STEP_ORDER],
}

# Mandatory ordering chain (spec 10.3).
_MANDATORY_CHAIN: tuple[str, ...] = (
    "select_authors",
    "select_books",
    "plan_preview_batch",
    "conflict_policy",
    "final_summary_confirm",
    "processing",
)


def load_or_bootstrap_wizard_definition(fs: FileService) -> dict[str, Any]:
    """Load WizardDefinition JSON, bootstrapping it if missing.

    The file is a runtime artifact located under the wizards root.
    """
    atomic_write_json_if_missing(
        fs,
        RootName.WIZARDS,
        WIZARD_DEFINITION_REL_PATH,
        DEFAULT_WIZARD_DEFINITION,
    )
    wd = read_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH)
    validate_wizard_definition_structure(wd)
    return wd


def validate_wizard_definition_structure(wd: Any) -> None:
    """Validate WizardDefinition v1/v2 structure and invariants."""
    if not isinstance(wd, dict):
        raise FinalizeError("wizard_definition must be a JSON object")

    wizard_id = wd.get("wizard_id")
    if wizard_id != "import":
        raise FinalizeError("wizard_definition wizard_id must be 'import'")

    version_any = wd.get("version")
    version = int(version_any) if isinstance(version_any, int) else 1

    if version == 1:
        _validate_v1_steps(wd)
        return

    if version == 2:
        _validate_v2_graph(wd)
        return

    raise FinalizeError("wizard_definition version must be 1 or 2")


def build_effective_workflow_snapshot(
    *,
    wizard_definition: dict[str, Any],
    flow_config: dict[str, Any],
) -> list[str]:
    """Return the effective ordered step_ids for a session.

    For v1 WizardDefinition, the ordering is derived from the steps list.
    For v2 WizardDefinition, the ordering is derived from graph.nodes order.

    Applies flow_config optional-step enable/disable rules.
    """
    version_any = wizard_definition.get("version")
    version = int(version_any) if isinstance(version_any, int) else 1

    ordered: list[str] = []

    if version == 1:
        steps_any = wizard_definition.get("steps")
        if not isinstance(steps_any, list):
            raise FinalizeError("wizard_definition steps must be a list")
        for s in steps_any:
            sid = s.get("step_id") if isinstance(s, dict) else None
            if not isinstance(sid, str) or not sid:
                raise FinalizeError("wizard_definition contains invalid step_id")
            if sid in OPTIONAL_STEP_IDS and not _is_enabled(sid, flow_config):
                continue
            ordered.append(sid)

        enforce_mandatory_constraints(ordered)
        return ordered

    if version == 2:
        graph_any = wizard_definition.get("graph")
        nodes_any = graph_any.get("nodes") if isinstance(graph_any, dict) else None
        if not isinstance(nodes_any, list):
            raise FinalizeError("wizard_definition graph nodes must be a list")

        for n in nodes_any:
            sid = n.get("step_id") if isinstance(n, dict) else None
            if not isinstance(sid, str) or not sid:
                raise FinalizeError("wizard_definition graph contains invalid step_id")
            if sid in OPTIONAL_STEP_IDS and not _is_enabled(sid, flow_config):
                continue
            ordered.append(sid)

        enforce_mandatory_constraints(ordered)
        return ordered

    raise FinalizeError("wizard_definition version must be 1 or 2")


def enforce_mandatory_constraints(step_order: list[str]) -> None:
    """Enforce mandatory constraints from specification section 10.3."""
    if not step_order:
        raise FinalizeError("wizard_definition step_order must be non-empty")
    if step_order[0] != "select_authors":
        raise FinalizeError("select_authors must be the first step")

    for sid in sorted(MANDATORY_STEP_IDS):
        if sid not in step_order:
            raise FinalizeError(f"wizard_definition missing mandatory step_id: {sid}")

    idxs = [step_order.index(sid) for sid in _MANDATORY_CHAIN]
    if idxs != sorted(idxs):
        raise FinalizeError("wizard_definition violates mandatory ordering constraints")

    # processing must be the only PHASE 2 step and the only terminal step.
    if step_order.count("processing") != 1:
        raise FinalizeError("wizard_definition must contain exactly one 'processing' step")
    if step_order[-1] != "processing":
        raise FinalizeError("wizard_definition processing must be the terminal step")


def _validate_v1_steps(wd: dict[str, Any]) -> None:
    steps_any = wd.get("steps")
    if not isinstance(steps_any, list) or not steps_any:
        raise FinalizeError("wizard_definition steps must be a non-empty list")

    known = _known_step_ids()

    seen: set[str] = set()
    for s in steps_any:
        if not isinstance(s, dict):
            raise FinalizeError("wizard_definition steps must be objects")
        sid = s.get("step_id")
        if not isinstance(sid, str) or not sid:
            raise FinalizeError("wizard_definition step_id must be a non-empty string")
        if sid in seen:
            raise FinalizeError("wizard_definition step_id must be unique")
        if sid not in known:
            raise FinalizeError(f"wizard_definition contains unknown step_id: {sid}")
        seen.add(sid)


def _validate_v2_graph(wd: dict[str, Any]) -> None:
    graph_any = wd.get("graph")
    if not isinstance(graph_any, dict):
        raise FinalizeError("wizard_definition graph must be an object")

    entry_any = graph_any.get("entry_step_id")
    if not isinstance(entry_any, str) or not entry_any:
        raise FinalizeError("wizard_definition graph entry_step_id must be a string")

    nodes_any = graph_any.get("nodes")
    if not isinstance(nodes_any, list) or not nodes_any:
        raise FinalizeError("wizard_definition graph nodes must be a non-empty list")

    known = _known_step_ids()

    nodes: list[str] = []
    seen: set[str] = set()
    for n in nodes_any:
        if not isinstance(n, dict):
            raise FinalizeError("wizard_definition graph nodes must be objects")
        sid = n.get("step_id")
        if not isinstance(sid, str) or not sid:
            raise FinalizeError("wizard_definition graph node step_id must be a string")
        if sid in seen:
            raise FinalizeError("wizard_definition graph node step_id must be unique")
        if sid not in known:
            raise FinalizeError(f"wizard_definition contains unknown step_id: {sid}")
        seen.add(sid)
        nodes.append(sid)

    if entry_any not in seen:
        raise FinalizeError("wizard_definition graph entry_step_id must exist in nodes")

    edges_any = graph_any.get("edges")
    if not isinstance(edges_any, list):
        raise FinalizeError("wizard_definition graph edges must be a list")

    outgoing: dict[str, list[dict[str, Any]]] = {sid: [] for sid in nodes}
    priorities_by_from: dict[str, set[int]] = {sid: set() for sid in nodes}

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

        outgoing.setdefault(str(frm), []).append(e)

        if "priority" not in e:
            raise FinalizeError("MISSING_PRIORITY: " + str(frm) + "->" + str(to))
        prio_any = e.get("priority")
        if not _is_strict_int(prio_any):
            raise FinalizeError(
                "AMBIGUOUS_TRANSITION: invalid_priority_type " + str(frm) + "->" + str(to)
            )
        prio = prio_any
        pri_set = priorities_by_from.setdefault(str(frm), set())
        if prio in pri_set:
            raise FinalizeError(
                "AMBIGUOUS_TRANSITION: duplicate_priority " + str(frm) + " priority=" + str(prio)
            )
        pri_set.add(prio)

        when_any = e.get("when")
        bad = find_invalid_condition_path(when_any)
        if bad is not None:
            raise FinalizeError("INVALID_CONDITION_PATH: " + bad + " " + str(frm) + "->" + str(to))

    for frm, out_edges in outgoing.items():
        unconditional = [x for x in out_edges if x.get("when") is None]
        if len(unconditional) > 1:
            raise FinalizeError(
                "AMBIGUOUS_TRANSITION: " + frm + " edges=" + str(len(unconditional))
            )

    _validate_v2_reachability(entry_any, nodes, edges_any)


def _validate_v2_reachability(entry: str, nodes: list[str], edges_any: list[Any]) -> None:
    adj: dict[str, set[str]] = {n: set() for n in nodes}
    for e in edges_any:
        if not isinstance(e, dict):
            continue
        frm = e.get("from_step_id")
        to = e.get("to_step_id")
        if isinstance(frm, str) and isinstance(to, str) and frm in adj and to in adj:
            adj[frm].add(to)

    # processing must exist, be reachable, and be terminal (no outgoing).
    if "processing" not in adj:
        raise FinalizeError("wizard_definition graph missing node: processing")

    reachable = _reachable_from(entry, adj)
    if "processing" not in reachable:
        raise FinalizeError("wizard_definition graph processing must be reachable from entry")
    if adj.get("processing"):
        raise FinalizeError("wizard_definition graph processing must be terminal")

    # Each mandatory step must be reachable from entry.
    for sid in sorted(MANDATORY_STEP_IDS):
        if sid not in reachable:
            raise FinalizeError(f"wizard_definition graph step not reachable: {sid}")

    # Mandatory chain must be ordered by reachability (path existence).
    chain = list(_MANDATORY_CHAIN)
    for a, b in zip(chain, chain[1:], strict=False):
        if b not in _reachable_from(a, adj):
            raise FinalizeError("wizard_definition graph violates mandatory chain reachability")


def _reachable_from(start: str, adj: dict[str, set[str]]) -> set[str]:
    seen: set[str] = set()
    stack: list[str] = [start]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for nxt in sorted(adj.get(cur, set())):
            if nxt not in seen:
                stack.append(nxt)
    return seen


def _known_step_ids() -> set[str]:
    # UI catalog step ids plus canonical defaults.
    return set(STEP_CATALOG.keys()) | set(CANONICAL_STEP_ORDER)


def _is_enabled(step_id: str, flow_config: dict[str, Any]) -> bool:
    steps_any = flow_config.get("steps") if isinstance(flow_config, dict) else None
    if not isinstance(steps_any, dict):
        return True
    cfg_any = steps_any.get(step_id)
    if not isinstance(cfg_any, dict):
        return True
    enabled = cfg_any.get("enabled")
    if enabled is None:
        return True
    return bool(enabled)


def _is_strict_int(v: Any) -> TypeGuard[int]:
    return isinstance(v, int) and not isinstance(v, bool)
