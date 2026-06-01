"""WizardDefinition model for the import wizard.

This module defines the default workflow ordering as data (Python-defined),
bootstraps a runtime JSON artifact under the wizards root if missing, and
produces an effective step ordering for session creation.

No repo JSON is authoritative.

ASCII-only.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TypeGuard, cast

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


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_dict_list(value: object) -> list[dict[str, object]]:
    if not _is_object_list(value):
        return []
    return [dict(item) for item in value if _is_str_object_dict(item)]


def _replace_expr_ref_inplace(node: object, *, old: str, new: str) -> None:
    if _is_str_object_dict(node):
        for key, value in list(node.items()):
            if key == "expr" and isinstance(value, str) and value == old:
                node[key] = new
                continue
            _replace_expr_ref_inplace(value, old=old, new=new)
        return
    if _is_object_list(node):
        for item in node:
            _replace_expr_ref_inplace(item, old=old, new=new)


def _migrate_v3_loop_step(
    wizard_definition: dict[str, object],
    *,
    old_step_id: str,
    loop_step_ids: tuple[str, ...],
    replaced_edge_from_step: str,
    replaced_expr_old: str,
    replaced_expr_new: str,
    shipped_default: dict[str, object],
) -> tuple[dict[str, object], bool]:
    nodes = _as_dict_list(wizard_definition.get("nodes"))
    node_ids = [str(node.get("step_id") or "") for node in nodes]
    if old_step_id not in node_ids or loop_step_ids[1] in node_ids:
        return wizard_definition, False
    if replaced_edge_from_step not in set(node_ids):
        return wizard_definition, False

    default_nodes = {
        str(node.get("step_id") or ""): dict(node)
        for node in _as_dict_list(shipped_default.get("nodes"))
        if isinstance(node.get("step_id"), str)
    }
    if not all(step_id in default_nodes for step_id in loop_step_ids):
        return wizard_definition, False

    migrated_nodes: list[dict[str, object]] = []
    inserted_loop = False
    loop_id_set = set(loop_step_ids)
    for node in nodes:
        step_id = str(node.get("step_id") or "")
        if step_id in loop_id_set:
            continue
        if step_id == old_step_id:
            migrated_nodes.extend(deepcopy(default_nodes[item_id]) for item_id in loop_step_ids)
            inserted_loop = True
            continue
        cloned_node = deepcopy(node)
        _replace_expr_ref_inplace(cloned_node, old=replaced_expr_old, new=replaced_expr_new)
        migrated_nodes.append(cloned_node)
    if not inserted_loop:
        return wizard_definition, False

    edges = _as_dict_list(wizard_definition.get("edges"))
    default_edges = _as_dict_list(shipped_default.get("edges"))

    filtered_edges: list[dict[str, object]] = []
    loop_target_ids = set(loop_step_ids)
    for edge in edges:
        from_step = str(edge.get("from") or "")
        to_step = str(edge.get("to") or "")
        if from_step == old_step_id or to_step == old_step_id:
            continue
        if from_step in loop_target_ids or to_step in loop_target_ids:
            continue
        if from_step == replaced_edge_from_step:
            continue
        filtered_edges.append(deepcopy(edge))

    loop_edge_sources = {replaced_edge_from_step, *loop_step_ids}
    migrated_edges = list(filtered_edges)
    migrated_edges.extend(
        deepcopy(edge) for edge in default_edges if str(edge.get("from") or "") in loop_edge_sources
    )

    migrated = dict(wizard_definition)
    migrated["nodes"] = migrated_nodes
    migrated["edges"] = migrated_edges
    return migrated, True


def _has_edge(
    edges: list[dict[str, object]],
    *,
    from_step: str,
    to_step: str,
    condition_expr: str | None,
) -> bool:
    for edge in edges:
        if str(edge.get("from") or "") != from_step:
            continue
        if str(edge.get("to") or "") != to_step:
            continue
        cond = edge.get("condition_expr")
        if condition_expr is None:
            if cond is None:
                return True
            continue
        cond_dict = _as_str_object_dict(cond)
        if str(cond_dict.get("expr") or "") == condition_expr:
            return True
    return False


def _migrate_v3_cover_loop(
    wizard_definition: dict[str, object],
) -> tuple[dict[str, object], bool]:
    if wizard_definition.get("version") != 3:
        return wizard_definition, False

    nodes = _as_dict_list(wizard_definition.get("nodes"))
    node_ids = {str(node.get("step_id") or "") for node in nodes}
    if "init_cover_loop" in node_ids:
        return wizard_definition, False
    required = {
        "covers_policy_mode",
        "covers_policy",
        "covers_policy_override_prepare",
        "covers_policy_url",
    }
    if not required.issubset(node_ids):
        return wizard_definition, False

    cover_nodes: list[dict[str, object]] = [
        {
            "step_id": "init_cover_loop",
            "op": {
                "primitive_id": "data.set",
                "primitive_version": 1,
                "inputs": {},
                "writes": [
                    {"to_path": "$.state.vars.cover_loop.index", "value": 0},
                    {
                        "to_path": "$.state.vars.cover_loop.confirmed",
                        "value": {"expr": "$.state.vars.phase1.cover.by_source_relative_path"},
                    },
                ],
            },
        },
        {
            "step_id": "cover_mode_item",
            "op": {
                "primitive_id": "ui.prompt_select",
                "primitive_version": 1,
                "inputs": {
                    "label": "Cover",
                    "prompt": "[book] Choose cover mode",
                    "help": "Choose cover source for the current book.",
                    "hint_expr": {
                        "expr": (
                            "$.state.vars.phase1.cover.per_source_hints[$.state.vars.cover_loop.index]"
                        )
                    },
                    "examples_expr": {
                        "expr": (
                            "$.state.vars.phase1.cover.per_source_allowed_modes"
                            "[$.state.vars.cover_loop.index]"
                        )
                    },
                    "prefill_expr": {
                        "expr": (
                            "$.state.vars.cover_loop.confirmed"
                            "[$.state.vars.phase1.select_books.selected_source_relative_paths"
                            "[$.state.vars.cover_loop.index]].kind"
                        )
                    },
                    "default_expr": {
                        "expr": (
                            "$.state.vars.cover_loop.confirmed"
                            "[$.state.vars.phase1.select_books.selected_source_relative_paths"
                            "[$.state.vars.cover_loop.index]].kind"
                        )
                    },
                },
                "writes": [
                    {
                        "to_path": "$.state.answers.cover_mode_item.value",
                        "value": {"expr": "$.op.outputs.selection"},
                    }
                ],
            },
        },
        {
            "step_id": "cover_mode_item_url",
            "op": {
                "primitive_id": "ui.prompt_text",
                "primitive_version": 1,
                "inputs": {
                    "label": "Cover URL or file path",
                    "prompt": "[book] Cover URL or file path (Enter=skip)",
                    "help": "Leave empty to skip cover override for current book.",
                    "prefill_expr": {
                        "expr": (
                            "$.state.vars.cover_loop.confirmed"
                            "[$.state.vars.phase1.select_books.selected_source_relative_paths"
                            "[$.state.vars.cover_loop.index]].url"
                        )
                    },
                    "default_expr": {
                        "expr": (
                            "$.state.vars.cover_loop.confirmed"
                            "[$.state.vars.phase1.select_books.selected_source_relative_paths"
                            "[$.state.vars.cover_loop.index]].url"
                        )
                    },
                    "examples": ["https://example.com/cover.jpg"],
                },
                "writes": [
                    {
                        "to_path": "$.state.answers.cover_mode_item_url.value",
                        "value": {"expr": "$.op.outputs.value"},
                    }
                ],
            },
        },
        {
            "step_id": "store_cover_item",
            "op": {
                "primitive_id": "data.set",
                "primitive_version": 1,
                "inputs": {},
                "writes": [
                    {
                        "to_path": "$.state.answers.store_cover_item.mode",
                        "value": {"expr": "$.state.answers.cover_mode_item.value"},
                    },
                    {
                        "to_path": "$.state.answers.store_cover_item.url",
                        "value": "",
                    },
                    {
                        "to_path": "$.state.vars.cover_loop.index",
                        "value": {"expr": "$.state.vars.cover_loop.index + 1"},
                    },
                ],
            },
        },
        {
            "step_id": "cover_loop_check",
            "op": {
                "primitive_id": "data.set",
                "primitive_version": 1,
                "inputs": {},
                "writes": [],
            },
        },
    ]

    migrated_nodes: list[dict[str, object]] = []
    inserted = False
    for node in nodes:
        migrated_nodes.append(deepcopy(node))
        if str(node.get("step_id") or "") == "covers_policy_mode":
            for cover_node in cover_nodes:
                migrated_nodes.append(deepcopy(cover_node))
            inserted = True
    if not inserted:
        return wizard_definition, False

    edges = _as_dict_list(wizard_definition.get("edges"))
    cover_step_ids = {
        "init_cover_loop",
        "cover_mode_item",
        "cover_mode_item_url",
        "store_cover_item",
        "cover_loop_check",
    }
    migrated_edges: list[dict[str, object]] = []
    for edge in edges:
        from_step = str(edge.get("from") or "")
        to_step = str(edge.get("to") or "")
        if from_step in cover_step_ids or to_step in cover_step_ids:
            continue
        migrated_edges.append(deepcopy(edge))

    def ensure_edge(*, from_step: str, to_step: str, condition_expr: str | None) -> None:
        if _has_edge(
            migrated_edges,
            from_step=from_step,
            to_step=to_step,
            condition_expr=condition_expr,
        ):
            return
        edge: dict[str, object] = {"from": from_step, "to": to_step}
        if condition_expr is not None:
            edge["condition_expr"] = {"expr": condition_expr}
        migrated_edges.append(edge)

    ensure_edge(
        from_step="covers_policy_mode",
        to_step="init_cover_loop",
        condition_expr="$.state.vars.human.covers_policy.mode == 'per_book'",
    )
    ensure_edge(from_step="init_cover_loop", to_step="cover_mode_item", condition_expr=None)
    ensure_edge(
        from_step="cover_mode_item",
        to_step="cover_mode_item_url",
        condition_expr="$.state.answers.cover_mode_item.value == 'url'",
    )
    ensure_edge(from_step="cover_mode_item", to_step="store_cover_item", condition_expr=None)
    ensure_edge(from_step="cover_mode_item_url", to_step="store_cover_item", condition_expr=None)
    ensure_edge(from_step="store_cover_item", to_step="cover_loop_check", condition_expr=None)
    ensure_edge(
        from_step="cover_loop_check",
        to_step="cover_mode_item",
        condition_expr=(
            "$.state.vars.cover_loop.index "
            "< len($.state.vars.phase1.select_books.selected_source_relative_paths)"
        ),
    )
    ensure_edge(
        from_step="cover_loop_check",
        to_step="covers_policy",
        condition_expr=(
            "$.state.vars.cover_loop.index "
            ">= len($.state.vars.phase1.select_books.selected_source_relative_paths)"
        ),
    )

    migrated = dict(wizard_definition)
    migrated["nodes"] = migrated_nodes
    migrated["edges"] = migrated_edges
    return migrated, True


def _normalize_v3_cover_loop_nodes(
    wizard_definition: dict[str, object],
) -> tuple[dict[str, object], bool]:
    if wizard_definition.get("version") != 3:
        return wizard_definition, False

    nodes = _as_dict_list(wizard_definition.get("nodes"))
    changed = False
    normalized_nodes: list[dict[str, object]] = []
    for node in nodes:
        step_id = str(node.get("step_id") or "")
        normalized = deepcopy(node)
        op = _as_str_object_dict(normalized.get("op"))
        inputs = _as_str_object_dict(op.get("inputs"))
        if step_id == "cover_mode_item":
            if "prefill_expr" in inputs:
                del inputs["prefill_expr"]
                changed = True
            if "default_expr" in inputs:
                del inputs["default_expr"]
                changed = True
            if inputs.get("default_value") != "skip":
                inputs["default_value"] = "skip"
                changed = True
            op["inputs"] = inputs
            normalized["op"] = op
        elif step_id == "cover_mode_item_url":
            if "prefill_expr" in inputs:
                del inputs["prefill_expr"]
                changed = True
            if "default_expr" in inputs:
                del inputs["default_expr"]
                changed = True
            if inputs.get("default_value") != "":
                inputs["default_value"] = ""
                changed = True
            op["inputs"] = inputs
            normalized["op"] = op
        elif step_id == "store_cover_item":
            writes_any = op.get("writes")
            writes = _as_dict_list(writes_any)
            normalized_writes: list[dict[str, object]] = []
            for write in writes:
                to_path = str(write.get("to_path") or "")
                if to_path == "$.state.answers.store_cover_item.url":
                    if write.get("value") != "":
                        changed = True
                    normalized_writes.append({"to_path": to_path, "value": ""})
                    continue
                normalized_writes.append(write)
            if normalized_writes:
                op["writes"] = normalized_writes
                normalized["op"] = op
        normalized_nodes.append(normalized)

    if not changed:
        return wizard_definition, False
    migrated = dict(wizard_definition)
    migrated["nodes"] = normalized_nodes
    return migrated, True


def _migrate_v3_phase1_loops(
    wizard_definition: dict[str, object],
) -> tuple[dict[str, object], bool]:
    if wizard_definition.get("version") != 3:
        return wizard_definition, False

    shipped_default = build_default_wizard_definition_v3()
    migrated_any = False
    migrated = dict(wizard_definition)

    migrated, migrated_author = _migrate_v3_loop_step(
        migrated,
        old_step_id="effective_author",
        loop_step_ids=(
            "init_author_loop",
            "effective_author_item",
            "store_author_item",
            "author_loop_check",
        ),
        replaced_edge_from_step="metadata_validate_initial",
        replaced_expr_old="$.state.answers.effective_author.author",
        replaced_expr_new="$.state.answers.store_author_item.author",
        shipped_default=shipped_default,
    )
    migrated_any = migrated_any or migrated_author

    migrated, migrated_title = _migrate_v3_loop_step(
        migrated,
        old_step_id="effective_title",
        loop_step_ids=(
            "init_title_loop",
            "effective_title_item",
            "store_title_item",
            "title_loop_check",
        ),
        replaced_edge_from_step="metadata_validate_after_author",
        replaced_expr_old="$.state.answers.effective_title.title",
        replaced_expr_new="$.state.answers.store_title_item.title",
        shipped_default=shipped_default,
    )
    migrated_any = migrated_any or migrated_title

    migrated, migrated_cover = _migrate_v3_cover_loop(migrated)
    migrated_any = migrated_any or migrated_cover

    migrated, normalized_cover = _normalize_v3_cover_loop_nodes(migrated)
    migrated_any = migrated_any or normalized_cover

    return migrated, migrated_any


# The default workflow definition is Python-defined and is used only for
# bootstrap if the runtime artifact is missing.
DEFAULT_WIZARD_DEFINITION: dict[str, object] = {
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


def _bootstrap_default_definition(version: int) -> dict[str, object]:
    if version == 3:
        return build_default_wizard_definition_v3()
    if version == 2:
        return DEFAULT_WIZARD_DEFINITION
    raise ValueError("bootstrap_default_version must be 2 or 3")


def _validated_bootstrap_definition(
    fs: FileService,
    *,
    bootstrap_default_version: int,
) -> dict[str, object]:
    default_definition = _bootstrap_default_definition(bootstrap_default_version)
    default_any = canonicalize_wizard_definition(default_definition)
    if not _is_str_object_dict(default_any):
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
) -> dict[str, object]:
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
    wd = _as_str_object_dict(read_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH))

    if wd.get("version") == 1:
        wd = migrate_v1_to_v2(wd)
        save_wizard_definition_with_history(fs, wd)

    try:
        validate_wizard_definition_structure(wd)
        wd_any = canonicalize_wizard_definition(wd)

        if not _is_str_object_dict(wd_any):
            raise ValueError("WizardDefinition must be an object")
        wd = wd_any

        wd, migrated = _migrate_v3_phase1_loops(wd)
        if migrated:
            wd_any = canonicalize_wizard_definition(wd)
            if not _is_str_object_dict(wd_any):
                raise ValueError("WizardDefinition must be an object")
            wd = wd_any
            save_wizard_definition_with_history(fs, wd)

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
    obj: dict[str, object],
    allowed: set[str],
    context: str,
) -> None:
    unknown = sorted(set(obj.keys()) - allowed)
    if unknown:
        raise FinalizeError(context + " contains unknown key(s): " + ", ".join(unknown))


def validate_wizard_definition_structure(wd: object) -> None:
    """Validate WizardDefinition v1/v2/v3 structure and invariants."""

    if not _is_str_object_dict(wd):
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


def canonicalize_wizard_definition(wd: object) -> object:
    """Return a canonicalized WizardDefinition.

    Canonicalization is ordering-only. For v2 WizardDefinition, edges are
    deterministically sorted by:
      (from_step_id ASC, priority ASC, to_step_id ASC)

    No nodes or edges are added or removed.
    """

    if not _is_str_object_dict(wd):
        return wd

    version_any = wd.get("version")
    version = int(version_any) if isinstance(version_any, int) else 1
    if version == 3:
        return canonicalize_wizard_definition_v3(wd)
    if version != 2:
        return wd

    graph_any = wd.get("graph")
    if not _is_str_object_dict(graph_any):
        return wd

    edges_any = graph_any.get("edges")
    if not _is_object_list(edges_any):
        return wd

    def edge_key(e: object) -> tuple[str, int, str]:
        if not _is_str_object_dict(e):
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


def migrate_v1_to_v2(wd: dict[str, object]) -> dict[str, object]:
    order: list[str] = []
    for step in _as_dict_list(wd.get("steps")):
        step_id = step.get("step_id")
        if isinstance(step_id, str) and step_id:
            order.append(step_id)
    if not order:
        order = list(CANONICAL_STEP_ORDER)
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
    wizard_definition: dict[str, object],
    flow_config: dict[str, object],
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
        if not _is_object_list(steps_any):
            raise FinalizeError("wizard_definition steps must be a list")
        steps = _as_dict_list(steps_any)
        if len(steps) != len(steps_any):
            raise FinalizeError("wizard_definition contains invalid step_id")
        for s in steps:
            sid = s.get("step_id")
            if not isinstance(sid, str) or not sid:
                raise FinalizeError("wizard_definition contains invalid step_id")
            if sid in OPTIONAL_STEP_IDS and not _is_enabled(sid, flow_config):
                continue
            ordered.append(sid)

        enforce_mandatory_constraints(ordered)
        return ordered

    if version == 2:
        graph_any = _as_str_object_dict(wizard_definition.get("graph"))
        nodes_any = graph_any.get("nodes")
        if not _is_object_list(nodes_any):
            raise FinalizeError("wizard_definition graph nodes must be a list")
        nodes = _as_dict_list(nodes_any)
        if len(nodes) != len(nodes_any):
            raise FinalizeError("wizard_definition graph contains invalid step_id")

        for n in nodes:
            sid = n.get("step_id")
            if not isinstance(sid, str) or not sid:
                raise FinalizeError("wizard_definition graph contains invalid step_id")
            if sid in OPTIONAL_STEP_IDS and not _is_enabled(sid, flow_config):
                continue
            ordered.append(sid)

        enforce_mandatory_constraints(ordered)
        return ordered

    if version == 3:
        nodes_any = wizard_definition.get("nodes")
        if not _is_object_list(nodes_any):
            raise FinalizeError("wizard_definition nodes must be a list")
        nodes = _as_dict_list(nodes_any)
        if len(nodes) != len(nodes_any):
            raise FinalizeError("wizard_definition contains invalid step_id")

        for n in nodes:
            sid = n.get("step_id")
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
    wizard_definition: dict[str, object],
    flow_config: dict[str, object],
) -> dict[str, object]:
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


def validate_wizard_definition_constraints_v2(wd: dict[str, object]) -> None:
    """Validate WizardDefinition v2 constraints that depend on node ordering.

    Ordering constraints are derived from graph.nodes order, not edges.
    """

    if wd.get("version") != 2:
        raise FinalizeError("wizard_definition must be version 2")

    graph_any = wd.get("graph")
    if not _is_str_object_dict(graph_any):
        raise FinalizeError("wizard_definition graph must be an object")

    nodes_any = graph_any.get("nodes")
    if not _is_object_list(nodes_any) or not nodes_any:
        raise FinalizeError("wizard_definition graph nodes must be a non-empty list")
    nodes = _as_dict_list(nodes_any)
    if len(nodes) != len(nodes_any):
        raise FinalizeError("wizard_definition graph nodes must be objects")

    step_order: list[str] = []
    for n in nodes:
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


def _validate_v1_steps(wd: dict[str, object]) -> None:
    steps_any = wd.get("steps")
    if not _is_object_list(steps_any) or not steps_any:
        raise FinalizeError("wizard_definition steps must be a non-empty list")
    steps = _as_dict_list(steps_any)
    if len(steps) != len(steps_any):
        raise FinalizeError("wizard_definition steps must be objects")

    known = _known_step_ids()

    seen: set[str] = set()
    for s in steps:
        sid = s.get("step_id")
        if not isinstance(sid, str) or not sid:
            raise FinalizeError("wizard_definition step_id must be a non-empty string")
        if sid in seen:
            raise FinalizeError("wizard_definition step_id must be unique")
        if sid not in known:
            raise FinalizeError(f"wizard_definition contains unknown step_id: {sid}")

        seen.add(sid)


def _validate_v2_graph(wd: dict[str, object]) -> None:
    graph_any = wd.get("graph")
    if not _is_str_object_dict(graph_any):
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
    if not _is_object_list(nodes_any) or not nodes_any:
        raise FinalizeError("wizard_definition graph nodes must be a non-empty list")
    nodes_raw = _as_dict_list(nodes_any)
    if len(nodes_raw) != len(nodes_any):
        raise FinalizeError("wizard_definition graph nodes must be objects")

    known = _known_step_ids()

    nodes: list[str] = []
    seen: set[str] = set()
    for n in nodes_raw:
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
    if not _is_object_list(edges_any):
        raise FinalizeError("wizard_definition graph edges must be a list")
    edges = _as_dict_list(edges_any)
    if len(edges) != len(edges_any):
        raise FinalizeError("wizard_definition graph edges must be objects")

    outgoing: dict[str, list[dict[str, object]]] = {sid: [] for sid in nodes}
    priorities_by_from: dict[str, set[int]] = {sid: set() for sid in nodes}

    for e in edges:
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

    _validate_v2_reachability(entry_any, nodes, edges)


def _validate_v2_reachability(
    entry: str,
    nodes: list[str],
    edges_any: list[dict[str, object]],
) -> None:
    adj: dict[str, set[str]] = {n: set() for n in nodes}
    for e in edges_any:
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


def _derived_legacy_catalog() -> dict[str, object]:
    projection = build_default_step_catalog_projection()
    steps: list[dict[str, object]] = []
    for step_id in projection:
        entry = projection[step_id]
        steps.append(
            {
                "step_id": step_id,
                "title": str(entry.get("title") or step_id),
                "computed_only": step_id in {"plan_preview_batch", "processing"},
                "fields": [],
            }
        )
    return {"version": 1, "steps": steps}


def _default_catalog_step_ids() -> tuple[str, ...]:
    projection = build_default_step_catalog_projection()
    return tuple(sorted(projection.keys()))


def _known_step_ids() -> set[str]:
    return set(_default_catalog_step_ids()) | set(CANONICAL_STEP_ORDER)


def _is_enabled(step_id: str, flow_config: dict[str, object]) -> bool:
    steps_any = flow_config.get("steps")
    if not _is_str_object_dict(steps_any):
        return True
    cfg_any = steps_any.get(step_id)
    if not _is_str_object_dict(cfg_any):
        return True
    enabled = cfg_any.get("enabled")
    if enabled is None:
        return True
    return bool(enabled)


def _is_strict_int(v: object) -> TypeGuard[int]:
    return isinstance(v, int) and not isinstance(v, bool)
