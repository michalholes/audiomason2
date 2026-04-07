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
from .dsl.default_wizard_v3 import build_default_wizard_definition_v3
from .dsl.wizard_definition_v3_model import (
    canonicalize_wizard_definition_v3,
    validate_wizard_definition_v3_structure,
)
from .errors import FinalizeError
from .field_schema_validation import FieldSchemaValidationError
from .flow_runtime import (
    CANONICAL_STEP_ORDER,
    MANDATORY_STEP_IDS,
    OPTIONAL_STEP_IDS,
    build_flow_model,
)
from .models import CatalogModel, FlowModel, validate_models
from .step_catalog import build_default_step_catalog_projection
from .storage import atomic_write_json_if_missing, read_json
from .wizard_definition_runtime_errors import invalid_authored_wizard_definition_error

WIZARD_DEFINITION_REL_PATH = "import/definitions/wizard_definition.json"


# The default workflow definition is Python-defined and is used only for
# bootstrap if the runtime artifact is missing.
DEFAULT_WIZARD_DEFINITION: dict[str, Any] = {
    "version": 2,
    "graph": {
        "entry_step_id": CANONICAL_STEP_ORDER[0],
        "nodes": [{"step_id": sid} for sid in CANONICAL_STEP_ORDER],
        "edges": [
            {
                "from_step_id": CANONICAL_STEP_ORDER[i],
                "to_step_id": CANONICAL_STEP_ORDER[i + 1],
                "priority": 0,
                "when": None,
            }
            for i in range(len(CANONICAL_STEP_ORDER) - 1)
        ],
    },
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


def _bootstrap_default_definition(version: int) -> dict[str, Any]:
    if version == 3:
        return build_default_wizard_definition_v3()
    if version == 2:
        return DEFAULT_WIZARD_DEFINITION
    raise ValueError("bootstrap_default_version must be 2 or 3")


def _validated_bootstrap_definition(
    fs: FileService,
    *,
    bootstrap_default_version: int,
) -> dict[str, Any]:
    default_definition = _bootstrap_default_definition(bootstrap_default_version)
    default_any = canonicalize_wizard_definition(default_definition)
    if not isinstance(default_any, dict):
        raise RuntimeError("default WizardDefinition must be an object")
    if default_any.get("version") != bootstrap_default_version:
        raise RuntimeError("default WizardDefinition version mismatch")
    if bootstrap_default_version == 2:
        validate_wizard_definition_constraints_v2(default_any)
        return default_any

    from .dsl.primitive_registry_storage import load_or_bootstrap_primitive_registry
    from .dsl.wizard_definition_v3_model import validate_wizard_definition_v3_against_registry

    registry = load_or_bootstrap_primitive_registry(fs)
    validate_wizard_definition_v3_against_registry(default_any, registry)
    return default_any


def load_or_bootstrap_wizard_definition(
    fs: FileService,
    *,
    bootstrap_default_version: int = 3,
) -> dict[str, Any]:
    """Load WizardDefinition JSON, bootstrapping it if missing.

    The file is a runtime artifact located under the wizards root.
    """

    from .wizard_editor_storage import save_wizard_definition_with_history

    default_definition = _validated_bootstrap_definition(
        fs,
        bootstrap_default_version=bootstrap_default_version,
    )

    atomic_write_json_if_missing(
        fs,
        RootName.WIZARDS,
        WIZARD_DEFINITION_REL_PATH,
        default_definition,
    )
    wd = read_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH)

    if wd.get("version") == 1:
        wd = migrate_v1_to_v2(wd)
        save_wizard_definition_with_history(fs, wd)

    try:
        validate_wizard_definition_structure(wd)
        wd = canonicalize_wizard_definition(wd)

        if not isinstance(wd, dict):
            raise ValueError("WizardDefinition must be an object")

        ver = wd.get("version")
        if ver == 2:
            validate_wizard_definition_constraints_v2(wd)
            return wd
        if ver == 3:
            from .dsl.primitive_registry_storage import load_or_bootstrap_primitive_registry
            from .dsl.wizard_definition_v3_model import (
                validate_wizard_definition_v3_against_registry,
            )

            registry = load_or_bootstrap_primitive_registry(fs)
            validate_wizard_definition_v3_against_registry(wd, registry)
            return wd

        raise ValueError("WizardDefinition must be version 2 or 3")
    except (FieldSchemaValidationError, FinalizeError, ValueError, TypeError) as exc:
        raise invalid_authored_wizard_definition_error(exc) from exc


def _assert_exact_keys(
    *,
    obj: dict[str, Any],
    allowed: set[str],
    context: str,
) -> None:
    unknown = sorted(set(obj.keys()) - allowed)
    if unknown:
        raise FinalizeError(context + " contains unknown key(s): " + ", ".join(unknown))


def validate_wizard_definition_structure(wd: Any) -> None:
    """Validate WizardDefinition v1/v2/v3 structure and invariants."""

    if not isinstance(wd, dict):
        raise FinalizeError("wizard_definition must be a JSON object")

    version_any = wd.get("version")
    version = int(version_any) if isinstance(version_any, int) else 1

    if version == 1:
        wizard_id = wd.get("wizard_id")
        if wizard_id is not None and wizard_id != "import":
            raise FinalizeError("wizard_definition wizard_id must be 'import'")
        _validate_v1_steps(wd)
        return

    if version == 2:
        if "wizard_id" in wd:
            raise FinalizeError("wizard_definition v2 prohibits wizard_id")
        _assert_exact_keys(obj=wd, allowed={"version", "graph"}, context="wizard_definition")
        _validate_v2_graph(wd)
        return

    if version == 3:
        validate_wizard_definition_v3_structure(wd)
        return

    raise FinalizeError("wizard_definition version must be 1, 2, or 3")


def canonicalize_wizard_definition(wd: Any) -> Any:
    """Return a canonicalized WizardDefinition.

    Canonicalization is ordering-only. For v2 WizardDefinition, edges are
    deterministically sorted by:
      (from_step_id ASC, priority ASC, to_step_id ASC)

    No nodes or edges are added or removed.
    """

    if not isinstance(wd, dict):
        return wd

    version_any = wd.get("version")
    version = int(version_any) if isinstance(version_any, int) else 1
    if version == 3:
        return canonicalize_wizard_definition_v3(wd)
    if version != 2:
        return wd

    graph_any = wd.get("graph")
    if not isinstance(graph_any, dict):
        return wd

    edges_any = graph_any.get("edges")
    if not isinstance(edges_any, list):
        return wd

    def edge_key(e: Any) -> tuple[str, int, str]:
        if not isinstance(e, dict):
            return ("", 0, "")
        frm = e.get("from_step_id")
        to = e.get("to_step_id")
        prio_any = e.get("priority")
        prio = int(prio_any) if isinstance(prio_any, int) else 0
        return (
            str(frm) if isinstance(frm, str) else "",
            prio,
            str(to) if isinstance(to, str) else "",
        )

    sorted_edges = sorted(list(edges_any), key=edge_key)
    graph = dict(graph_any)
    graph["edges"] = sorted_edges
    out = dict(wd)
    out["graph"] = graph
    return out


def migrate_v1_to_v2(wd: dict[str, Any]) -> dict[str, Any]:
    order = [s["step_id"] for s in wd.get("steps", [])] or CANONICAL_STEP_ORDER
    return {
        "version": 2,
        "graph": {
            "entry_step_id": order[0],
            "nodes": [{"step_id": sid} for sid in order],
            "edges": [
                {
                    "from_step_id": order[i],
                    "to_step_id": order[i + 1],
                    "priority": 0,
                    "when": None,
                }
                for i in range(len(order) - 1)
            ],
        },
    }


def build_effective_workflow_snapshot(
    *,
    wizard_definition: dict[str, Any],
    flow_config: dict[str, Any],
) -> list[str]:
    """Return the effective ordered step_ids for a session.

    For v1 WizardDefinition, the ordering is derived from the steps list.
    For v2 WizardDefinition, the ordering is derived from graph.nodes order.
    For v3 WizardDefinition, the ordering is derived from nodes order.

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

    if version == 3:
        nodes_any = wizard_definition.get("nodes")
        if not isinstance(nodes_any, list):
            raise FinalizeError("wizard_definition nodes must be a list")

        for n in nodes_any:
            sid = n.get("step_id") if isinstance(n, dict) else None
            if not isinstance(sid, str) or not sid:
                raise FinalizeError("wizard_definition contains invalid step_id")
            if sid in OPTIONAL_STEP_IDS and not _is_enabled(sid, flow_config):
                continue
            ordered.append(sid)

        enforce_mandatory_constraints(ordered)
        return ordered

    raise FinalizeError("wizard_definition version must be 1, 2, or 3")


def build_legacy_runtime_flow_model_from_definition(
    *,
    wizard_definition: dict[str, Any],
    flow_config: dict[str, Any],
) -> dict[str, Any]:
    """Build a legacy runtime FlowModel without persisted legacy JSON authority."""

    step_order = build_effective_workflow_snapshot(
        wizard_definition=wizard_definition,
        flow_config=flow_config,
    )
    catalog = CatalogModel.from_dict(_derived_legacy_catalog())
    flow = FlowModel.from_dict(
        {
            "version": 1,
            "entry_step_id": step_order[0],
            "nodes": [
                {
                    "step_id": sid,
                    "next_step_id": step_order[index + 1] if index + 1 < len(step_order) else None,
                    "prev_step_id": step_order[index - 1] if index > 0 else None,
                }
                for index, sid in enumerate(step_order)
            ],
        }
    )
    validate_models(catalog, flow)
    return build_flow_model(
        catalog=catalog,
        flow_config=flow_config,
        step_order=step_order,
    )


def validate_wizard_definition_constraints_v2(wd: dict[str, Any]) -> None:
    """Validate WizardDefinition v2 constraints that depend on node ordering.

    Ordering constraints are derived from graph.nodes order, not edges.
    """

    if wd.get("version") != 2:
        raise FinalizeError("wizard_definition must be version 2")

    graph_any = wd.get("graph")
    if not isinstance(graph_any, dict):
        raise FinalizeError("wizard_definition graph must be an object")

    nodes_any = graph_any.get("nodes")
    if not isinstance(nodes_any, list) or not nodes_any:
        raise FinalizeError("wizard_definition graph nodes must be a non-empty list")

    step_order: list[str] = []
    for n in nodes_any:
        if not isinstance(n, dict):
            raise FinalizeError("wizard_definition graph nodes must be objects")
        sid = n.get("step_id")
        if not isinstance(sid, str) or not sid:
            raise FinalizeError("wizard_definition graph node step_id must be a string")
        step_order.append(sid)

    enforce_mandatory_constraints(step_order)


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
        # Provide a deterministic, specific error to help users fix ordering.
        pos = {sid: step_order.index(sid) for sid in _MANDATORY_CHAIN}
        for i in range(len(_MANDATORY_CHAIN) - 1):
            a = _MANDATORY_CHAIN[i]
            b = _MANDATORY_CHAIN[i + 1]
            if pos[a] > pos[b]:
                msg = (
                    "wizard_definition ordering violated: "
                    + a
                    + " must be before "
                    + b
                    + " (positions "
                    + str(pos[a])
                    + ">"
                    + str(pos[b])
                    + ")"
                )
                raise FinalizeError(msg)
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

    _assert_exact_keys(
        obj=graph_any,
        allowed={"entry_step_id", "nodes", "edges"},
        context="wizard_definition graph",
    )

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

        _assert_exact_keys(obj=n, allowed={"step_id"}, context="wizard_definition graph node")

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

        _assert_exact_keys(
            obj=e,
            allowed={"from_step_id", "to_step_id", "priority", "when"},
            context="wizard_definition graph edge",
        )

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

    # If processing exists, it must be reachable and terminal (no outgoing).
    if "processing" in adj:
        reachable = _reachable_from(entry, adj)
        if "processing" not in reachable:
            raise FinalizeError("wizard_definition graph processing must be reachable from entry")
        if adj.get("processing"):
            raise FinalizeError("wizard_definition graph processing must be terminal")

    reachable = _reachable_from(entry, adj)
    # Each mandatory step that exists must be reachable from entry.
    for sid in sorted(MANDATORY_STEP_IDS):
        if sid in adj and sid not in reachable:
            raise FinalizeError(f"wizard_definition graph step not reachable: {sid}")

    # Mandatory chain must be ordered by reachability (path existence) when both steps exist.
    chain = list(_MANDATORY_CHAIN)
    for a, b in zip(chain, chain[1:], strict=False):
        if a in adj and b in adj and b not in _reachable_from(a, adj):
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


def _derived_legacy_catalog() -> dict[str, Any]:
    projection = build_default_step_catalog_projection()
    steps = [
        {
            "step_id": step_id,
            "title": str(entry.get("title") or step_id),
            "computed_only": False,
            "fields": [],
        }
        for step_id, entry in sorted(projection.items())
    ]
    return {"version": 1, "steps": steps}


def _default_catalog_step_ids() -> tuple[str, ...]:
    projection = build_default_step_catalog_projection()
    return tuple(sorted(projection.keys()))


def _known_step_ids() -> set[str]:
    return set(_default_catalog_step_ids()) | set(CANONICAL_STEP_ORDER)


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
