"""Import plugin: StepCatalog (UI-only step metadata).

This is a read-only catalog used by UI editors.
It must be deterministic and ASCII-only.
"""

from __future__ import annotations

from typing import Any

from .defaults import DEFAULT_CATALOG, DEFAULT_FLOW_CONFIG
from .errors import FinalizeError
from .flow_runtime import CANONICAL_STEP_ORDER


def _field(
    *,
    key: str,
    type_name: str,
    required: bool = False,
    default: Any = "",
) -> dict[str, Any]:
    return {
        "key": key,
        "type": type_name,
        "required": bool(required),
        "default": default,
    }


def _schema(fields: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": 1,
        "fields": list(fields),
    }


# Legacy UI fallback metadata.
#
# Notes:
# - active projection authority comes from WizardDefinition plus FlowConfig
# - settings_schema + defaults_template are UI-only and do not affect runtime
# - keep descriptions short and deterministic
STEP_CATALOG: dict[str, dict[str, Any]] = {
    "select_authors": {
        "id": "select_authors",
        "title": "Select Authors",
        "displayName": "Select Authors",
        "description": "Choose authors to include in the import session.",
        "behavioralSummary": "User selects authors for the session plan.",
        "inputContract": "Requires available authors in the chosen root/path.",
        "outputContract": "Produces a selected author set for downstream steps.",
        "sideEffectsDescription": "No side effects. UI-only selection.",
        "settings_schema": _schema([]),
        "defaults_template": {},
    },
    "select_books": {
        "id": "select_books",
        "title": "Select Books",
        "displayName": "Select Books",
        "description": "Choose which books to import for the selected authors.",
        "behavioralSummary": "User selects books to include for selected authors.",
        "inputContract": "Requires authors selected in prior step.",
        "outputContract": "Produces a selected book set for downstream planning.",
        "sideEffectsDescription": "No side effects. UI-only selection.",
        "settings_schema": _schema([]),
        "defaults_template": {},
    },
    "plan_preview_batch": {
        "id": "plan_preview_batch",
        "title": "Plan Preview",
        "displayName": "Plan Preview",
        "description": "Preview the planned operations before applying policies.",
        "behavioralSummary": "Shows a preview of planned operations for review.",
        "inputContract": "Requires selected authors and books.",
        "outputContract": "Produces a plan snapshot for policy steps.",
        "sideEffectsDescription": "No side effects. UI-only preview.",
        "settings_schema": _schema([]),
        "defaults_template": {},
    },
    "effective_author_title": {
        "id": "effective_author_title",
        "title": "Effective Author Title",
        "displayName": "Effective Author Title",
        "description": "Show the effective author/title values computed for the plan.",
        "behavioralSummary": "Displays computed effective author/title values.",
        "inputContract": "Requires a computed plan snapshot.",
        "outputContract": "Provides visibility into computed naming inputs.",
        "sideEffectsDescription": "No side effects. UI-only display.",
        "settings_schema": _schema([]),
        "defaults_template": {},
    },
    "filename_policy": {
        "id": "filename_policy",
        "title": "Filename Policy",
        "displayName": "Filename Policy",
        "description": "Define filename normalization and naming behavior.",
        "behavioralSummary": "Configures filename policy used during processing.",
        "inputContract": "Accepts policy settings for naming and normalization.",
        "outputContract": "Produces filename policy settings for runtime.",
        "sideEffectsDescription": "No side effects until processing runs.",
        "settings_schema": _schema(
            [
                _field(key="hint", type_name="string", required=False, default=""),
            ]
        ),
        "defaults_template": {"hint": ""},
    },
    "covers_policy": {
        "id": "covers_policy",
        "title": "Covers Policy",
        "displayName": "Covers Policy",
        "description": "Define how cover images are selected and applied.",
        "behavioralSummary": "Configures cover image selection and application.",
        "inputContract": "Accepts settings for cover selection rules.",
        "outputContract": "Produces cover policy settings for runtime.",
        "sideEffectsDescription": "No side effects until processing runs.",
        "settings_schema": _schema(
            [
                _field(key="hint", type_name="string", required=False, default=""),
            ]
        ),
        "defaults_template": {"hint": ""},
    },
    "id3_policy": {
        "id": "id3_policy",
        "title": "ID3 Policy",
        "displayName": "ID3 Policy",
        "description": "Define how ID3 tags are written for audio outputs.",
        "behavioralSummary": "Configures ID3 tag writing behavior for audio.",
        "inputContract": "Accepts settings for ID3 tag mapping and writing.",
        "outputContract": "Produces ID3 policy settings for runtime.",
        "sideEffectsDescription": "No side effects until processing runs.",
        "settings_schema": _schema(
            [
                _field(key="hint", type_name="string", required=False, default=""),
            ]
        ),
        "defaults_template": {"hint": ""},
    },
    "audio_processing": {
        "id": "audio_processing",
        "title": "Audio Processing",
        "displayName": "Audio Processing",
        "description": "Configure audio processing options used during import.",
        "behavioralSummary": "Configures audio processing options and behavior.",
        "inputContract": "Accepts audio processing settings.",
        "outputContract": "Produces audio processing settings for runtime.",
        "sideEffectsDescription": "No side effects until processing runs.",
        "settings_schema": _schema(
            [
                _field(key="hint", type_name="string", required=False, default=""),
            ]
        ),
        "defaults_template": {"hint": ""},
    },
    "publish_policy": {
        "id": "publish_policy",
        "title": "Publish Policy",
        "displayName": "Publish Policy",
        "description": "Define how results are published after processing.",
        "behavioralSummary": "Configures publishing behavior after processing.",
        "inputContract": "Accepts settings that control publishing actions.",
        "outputContract": "Produces publish policy settings for runtime.",
        "sideEffectsDescription": "May publish outputs during processing.",
        "settings_schema": _schema(
            [
                _field(key="hint", type_name="string", required=False, default=""),
            ]
        ),
        "defaults_template": {"hint": ""},
    },
    "delete_source_policy": {
        "id": "delete_source_policy",
        "title": "Delete Source Policy",
        "displayName": "Delete Source Policy",
        "description": "Define whether and when source files may be deleted.",
        "behavioralSummary": "Configures deletion behavior for source files.",
        "inputContract": "Accepts settings controlling deletion conditions.",
        "outputContract": "Produces delete policy settings for runtime.",
        "sideEffectsDescription": "May delete source files during processing.",
        "settings_schema": _schema(
            [
                _field(key="hint", type_name="string", required=False, default=""),
            ]
        ),
        "defaults_template": {"hint": ""},
    },
    "conflict_policy": {
        "id": "conflict_policy",
        "title": "Conflict Policy",
        "displayName": "Conflict Policy",
        "description": "Define conflict detection and resolution behavior.",
        "behavioralSummary": "Configures conflict detection and resolution rules.",
        "inputContract": "Accepts settings for conflict policy and prefill.",
        "outputContract": "Produces conflict policy settings for runtime.",
        "sideEffectsDescription": "No side effects until processing runs.",
        "settings_schema": _schema(
            [
                _field(key="hint", type_name="string", required=False, default=""),
                _field(
                    key="prefill_policy",
                    type_name="string",
                    required=False,
                    default="",
                ),
            ]
        ),
        "defaults_template": {"hint": "", "prefill_policy": ""},
    },
    "parallelism": {
        "id": "parallelism",
        "title": "Parallelism",
        "displayName": "Parallelism",
        "description": "Configure concurrency limits for processing jobs.",
        "behavioralSummary": "Configures concurrency limits for job execution.",
        "inputContract": "Accepts integer concurrency configuration values.",
        "outputContract": "Produces parallelism settings for runtime.",
        "sideEffectsDescription": "No side effects. Limits apply during processing.",
        "settings_schema": _schema(
            [
                _field(key="max_jobs", type_name="int", required=False, default=0),
            ]
        ),
        "defaults_template": {"max_jobs": 0},
    },
    "final_summary_confirm": {
        "id": "final_summary_confirm",
        "title": "Final Summary",
        "displayName": "Final Summary",
        "description": "Review the final plan summary and confirm execution.",
        "behavioralSummary": "User confirms the final plan summary before run.",
        "inputContract": "Requires a computed plan snapshot and applied policies.",
        "outputContract": "Produces a confirmation to proceed to processing.",
        "sideEffectsDescription": "No side effects. Confirmation gates processing.",
        "settings_schema": _schema([]),
        "defaults_template": {},
    },
    "resolve_conflicts_batch": {
        "id": "resolve_conflicts_batch",
        "title": "Resolve Conflicts",
        "displayName": "Resolve Conflicts",
        "description": "Resolve conflicts when conflict resolution is required.",
        "behavioralSummary": "User resolves detected conflicts for the plan.",
        "inputContract": "Requires conflicts detected by prior planning.",
        "outputContract": "Produces resolved conflict decisions.",
        "sideEffectsDescription": "No side effects until processing runs.",
        "settings_schema": _schema([]),
        "defaults_template": {},
    },
    "processing": {
        "id": "processing",
        "title": "Processing",
        "displayName": "Processing",
        "description": "Execute processing jobs and show progress.",
        "behavioralSummary": "Runs processing jobs and reports progress.",
        "inputContract": "Requires validated configuration and wizard definition.",
        "outputContract": "Produces job execution and output artifacts.",
        "sideEffectsDescription": "Performs processing work and writes outputs.",
        "settings_schema": _schema([]),
        "defaults_template": {},
    },
}


def get_step_details(step_id: str) -> dict[str, Any] | None:
    """Return legacy editor fallback metadata only.

    This helper is UI-only. Runtime and validation must not treat it as
    authority. Active editor surfaces should prefer build_step_catalog_projection().
    """

    return STEP_CATALOG.get(step_id)


def build_authority_known_step_ids() -> set[str]:
    """Return a legacy compatibility-only step id snapshot.

    Runtime authority must derive step ids from the active wizard definition.
    This helper remains projection-only for legacy callers that still need the
    default catalog view.
    """

    return set(_legacy_catalog_step_ids()) | set(CANONICAL_STEP_ORDER)


def _legacy_catalog_step_ids() -> tuple[str, ...]:
    steps_any = DEFAULT_CATALOG.get("steps")
    if not isinstance(steps_any, list):
        raise FinalizeError("default catalog steps must be a list")

    step_ids: list[str] = []
    for step in steps_any:
        if not isinstance(step, dict):
            raise FinalizeError("default catalog step must be an object")
        step_id = step.get("step_id")
        if not isinstance(step_id, str) or not step_id:
            raise FinalizeError("default catalog step_id must be a non-empty string")
        step_ids.append(step_id)
    return tuple(step_ids)


def build_default_step_catalog_projection() -> dict[str, dict[str, Any]]:
    defaults_any = DEFAULT_FLOW_CONFIG.get("defaults")
    step_defaults_map = defaults_any if isinstance(defaults_any, dict) else {}
    projection: dict[str, dict[str, Any]] = {}
    for step_id in _legacy_catalog_step_ids():
        defaults_obj = step_defaults_map.get(step_id)
        step_defaults = defaults_obj if isinstance(defaults_obj, dict) else {}
        projection[step_id] = _project_v2_step(step_id, step_defaults)
    return projection


_PROMPT_FIELD_ORDER: tuple[str, ...] = (
    "label",
    "prompt",
    "help",
    "hint",
    "examples",
    "default_value",
    "prefill",
    "default_expr",
    "prefill_expr",
    "autofill_if",
)


def _humanize_step_id(step_id: str) -> str:
    return " ".join(part.capitalize() for part in step_id.split("_") if part) or step_id


def _field_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    return "json"


def _schema_from_mapping(data: dict[str, Any]) -> dict[str, Any]:
    fields = [
        {"key": key, "type": _field_type(value), "required": False, "default": value}
        for key, value in sorted(data.items())
    ]
    return _schema(fields)


def _project_v2_step(step_id: str, step_defaults: dict[str, Any]) -> dict[str, Any]:
    title = _humanize_step_id(step_id)
    defaults_template = dict(step_defaults)
    return {
        "id": step_id,
        "step_id": step_id,
        "title": title,
        "displayName": title,
        "description": "Derived from the active WizardDefinition v2 graph.",
        "behavioralSummary": "Read-only projection from the active import authority.",
        "inputContract": "Derived from active WizardDefinition and FlowConfig.",
        "outputContract": "Projection-only step metadata for editor surfaces.",
        "sideEffectsDescription": "No side effects. Projection only.",
        "settings_schema": _schema_from_mapping(defaults_template),
        "defaults_template": defaults_template,
    }


def _project_v3_step(step: dict[str, Any], step_defaults: dict[str, Any]) -> dict[str, Any]:
    step_id = str(step.get("step_id") or "")
    ui_any = step.get("ui")
    ui: dict[str, Any] = dict(ui_any) if isinstance(ui_any, dict) else {}
    display_name = str(ui.get("label") or step_id or _humanize_step_id(step_id))
    defaults_template = {key: ui[key] for key in _PROMPT_FIELD_ORDER if key in ui}
    fields_data = dict(defaults_template)
    fields_data.update(step_defaults)
    primitive_id = str(step.get("primitive_id") or "")
    description = str(ui.get("prompt") or primitive_id or "")
    return {
        "id": step_id,
        "step_id": step_id,
        "title": display_name,
        "displayName": display_name,
        "description": description or "Derived from the active WizardDefinition v3 graph.",
        "behavioralSummary": "Read-only projection from the active import authority.",
        "inputContract": "Derived from active WizardDefinition and FlowConfig.",
        "outputContract": "Projection-only step metadata for editor surfaces.",
        "sideEffectsDescription": "No side effects. Projection only.",
        "settings_schema": _schema_from_mapping(fields_data),
        "defaults_template": defaults_template,
    }


def build_step_catalog_projection(
    *, wizard_definition: dict[str, Any], flow_config: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    if not isinstance(wizard_definition, dict):
        raise FinalizeError("wizard_definition must be an object")
    if not isinstance(flow_config, dict):
        raise FinalizeError("flow_config must be an object")

    defaults_any = flow_config.get("defaults")
    step_defaults_map = defaults_any if isinstance(defaults_any, dict) else {}
    version = wizard_definition.get("version")

    if version == 3:
        from .dsl.flowmodel_v3 import build_flow_model_v3

        flow_model = build_flow_model_v3(wizard_definition=wizard_definition)
        out_v3: dict[str, dict[str, Any]] = {}
        steps_any = flow_model.get("steps")
        if not isinstance(steps_any, list):
            raise FinalizeError("flow_model steps must be a list")
        for step_any in steps_any:
            if not isinstance(step_any, dict):
                raise FinalizeError("flow_model step must be an object")
            step_id = str(step_any.get("step_id") or "")
            if not step_id:
                raise FinalizeError("flow_model step_id must be a non-empty string")
            defaults_any = step_defaults_map.get(step_id)
            step_defaults = defaults_any if isinstance(defaults_any, dict) else {}
            out_v3[step_id] = _project_v3_step(step_any, step_defaults)
        return out_v3

    if version != 2:
        raise FinalizeError("wizard_definition must be version 2 or 3")

    graph = wizard_definition.get("graph")
    if not isinstance(graph, dict):
        raise FinalizeError("wizard_definition graph must be an object")
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        raise FinalizeError("wizard_definition graph.nodes must be a list")

    out: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            raise FinalizeError("wizard_definition graph node must be an object")
        step_id_any = node.get("step_id")
        if not isinstance(step_id_any, str) or not step_id_any:
            raise FinalizeError("wizard_definition graph node step_id must be a string")
        defaults_any = step_defaults_map.get(step_id_any)
        step_defaults = defaults_any if isinstance(defaults_any, dict) else {}
        out[step_id_any] = _project_v2_step(step_id_any, step_defaults)
    return out
