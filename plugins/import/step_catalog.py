"""Import plugin: StepCatalog (UI-only step metadata).

This is a read-only catalog used by UI editors.
It must be deterministic and ASCII-only.
"""

from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from typing import Any

from .defaults import DEFAULT_FLOW_CONFIG
from .dsl.default_wizard_v3 import build_default_wizard_definition_v3
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

# Legacy UI fallback metadata must remain derived from the active authority.
# Keep descriptions short and deterministic.


def _projected_defaults_template(step_id: str, *, ui_fields: dict[str, Any]) -> dict[str, Any]:
    defaults_template = {key: ui_fields[key] for key in _PROMPT_FIELD_ORDER if key in ui_fields}
    if defaults_template:
        return defaults_template
    ui_only_steps = {
        "plan_preview_batch",
        "final_summary_confirm",
        "resolve_conflicts_batch",
        "processing",
    }
    if step_id in ui_only_steps:
        return {}
    if step_id == "parallelism":
        return {"max_jobs": 0}
    if step_id == "skip_processed_books":
        return {"mode": "skip"}
    return {"hint": ""}


def _projected_step_catalog_entry(
    step_id: str,
    *,
    ui_fields: dict[str, Any],
    flow_defaults: dict[str, Any],
) -> dict[str, Any]:
    display_name = str(ui_fields.get("label") or _humanize_step_id(step_id))
    description = str(ui_fields.get("prompt") or "Derived from the active import authority.")
    defaults_template = _projected_defaults_template(step_id, ui_fields=ui_fields)
    schema_inputs = dict(defaults_template)
    schema_inputs.update(flow_defaults)
    return {
        "id": step_id,
        "step_id": step_id,
        "title": display_name,
        "displayName": display_name,
        "description": description,
        "behavioralSummary": "Read-only projection from the active import authority.",
        "inputContract": "Derived from active WizardDefinition and FlowConfig.",
        "outputContract": "Projection-only step metadata for editor surfaces.",
        "sideEffectsDescription": "No side effects. Projection only.",
        "settings_schema": _schema_from_mapping(schema_inputs),
        "defaults_template": defaults_template,
    }


class _DerivedStepCatalogView(MutableMapping[str, dict[str, Any]]):
    def __init__(self) -> None:
        self._overrides: dict[str, dict[str, Any]] = {}

    def _base(self) -> dict[str, dict[str, Any]]:
        return build_default_step_catalog_projection()

    def _merged(self) -> dict[str, dict[str, Any]]:
        merged = self._base()
        merged.update(self._overrides)
        return merged

    def __getitem__(self, key: str) -> dict[str, Any]:
        merged = self._merged()
        if key not in merged:
            raise KeyError(key)
        return merged[key]

    def __setitem__(self, key: str, value: dict[str, Any]) -> None:
        self._overrides[key] = value

    def __delitem__(self, key: str) -> None:
        if key in self._overrides:
            del self._overrides[key]
            return
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(self._merged())

    def __len__(self) -> int:
        return len(self._merged())

    def get(self, key: str, default: Any = None) -> Any:
        return self._merged().get(key, default)

    def pop(self, key: str, default: Any = None) -> Any:
        if key in self._overrides:
            return self._overrides.pop(key)
        if default is not None:
            return default
        raise KeyError(key)


STEP_CATALOG: MutableMapping[str, dict[str, Any]] = _DerivedStepCatalogView()


def get_step_details(step_id: str) -> dict[str, Any] | None:
    """Return a derived default projection entry for legacy UI callers only."""

    return build_default_step_catalog_projection().get(step_id)


def build_authority_known_step_ids() -> set[str]:
    """Return a derived compatibility-only step id snapshot."""

    return set(build_default_step_catalog_projection()) | set(CANONICAL_STEP_ORDER)


def _legacy_catalog_step_ids() -> tuple[str, ...]:
    definition = build_default_wizard_definition_v3()
    nodes_any = definition.get("nodes")
    if not isinstance(nodes_any, list):
        raise FinalizeError("default wizard_definition nodes must be a list")
    step_ids: list[str] = []
    for node_any in nodes_any:
        if not isinstance(node_any, dict):
            raise FinalizeError("default wizard_definition node must be an object")
        step_id = node_any.get("step_id")
        if not isinstance(step_id, str) or not step_id:
            raise FinalizeError("default wizard_definition step_id must be a non-empty string")
        if step_id not in step_ids:
            step_ids.append(step_id)
    return tuple(step_ids)


def build_default_step_catalog_projection() -> dict[str, dict[str, Any]]:
    """Return a deterministic compatibility projection derived from authority inputs."""

    projected = build_step_catalog_projection(
        wizard_definition=build_default_wizard_definition_v3(),
        flow_config=DEFAULT_FLOW_CONFIG,
    )
    return {step_id: projected[step_id] for step_id in CANONICAL_STEP_ORDER if step_id in projected}


_PROMPT_FIELD_ORDER: tuple[str, ...] = (
    "label",
    "prompt",
    "help",
    "hint",
    "examples",
    "label_expr",
    "prompt_expr",
    "help_expr",
    "hint_expr",
    "examples_expr",
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
    primitive_id = str(step.get("primitive_id") or "")
    entry = _projected_step_catalog_entry(
        step_id,
        ui_fields=ui,
        flow_defaults=step_defaults,
    )
    if not str(entry.get("description") or "") and primitive_id:
        entry["description"] = primitive_id
    return entry


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
        projected = _project_v2_step(step_id_any, step_defaults)
        out[step_id_any] = projected
    return out
