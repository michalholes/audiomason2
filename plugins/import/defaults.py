"""De-structuralized compatibility defaults for the import plugin.

This module keeps only in-memory compatibility data and FlowConfig re-exports.
Persisted legacy JSON files under import/catalog/ and import/flow/ are not
runtime authority and must not be created here.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from plugins.file_io.service import FileService

from .flow_config_defaults import DEFAULT_FLOW_CONFIG, ensure_flow_config_exists

__all__ = ["DEFAULT_CATALOG", "DEFAULT_FLOW_CONFIG", "ensure_default_models"]


def _make_default_steps() -> list[dict[str, Any]]:
    required_order = [
        "select_authors",
        "select_books",
        "plan_preview_batch",
        "effective_author_title",
        "filename_policy",
        "covers_policy",
        "id3_policy",
        "audio_processing",
        "publish_policy",
        "delete_source_policy",
        "skip_processed_books",
        "conflict_policy",
        "parallelism",
        "final_summary_confirm",
        "resolve_conflicts_batch",
        "processing",
    ]

    steps: list[dict[str, Any]] = []
    for step_id in required_order:
        computed_only = step_id in {"plan_preview_batch", "processing"}
        steps.append(
            {
                "step_id": step_id,
                "title": step_id.replace("_", " ").title(),
                "computed_only": computed_only,
                "fields": _default_fields_for_step(step_id),
            }
        )

    return steps


def _default_fields_for_step(step_id: str) -> list[dict[str, Any]]:
    if step_id == "select_authors":
        return [
            {
                "name": "selection",
                "type": "multi_select_indexed",
                "required": True,
                "constraints": {},
                "items": [],
            }
        ]
    if step_id == "select_books":
        return [
            {
                "name": "selection",
                "type": "multi_select_indexed",
                "required": True,
                "constraints": {},
                "items": [],
            }
        ]
    if step_id in {"plan_preview_batch", "processing"}:
        return []
    if step_id == "final_summary_confirm":
        return [
            {
                "name": "confirm_start",
                "type": "confirm",
                "required": True,
                "constraints": {},
            }
        ]
    if step_id == "resolve_conflicts_batch":
        return [
            {
                "name": "confirm",
                "type": "confirm",
                "required": True,
                "constraints": {},
            }
        ]
    if step_id == "skip_processed_books":
        return [
            {
                "name": "mode",
                "type": "text",
                "required": True,
                "constraints": {},
            }
        ]
    if step_id == "parallelism":
        return [
            {
                "name": "workers",
                "type": "number",
                "required": True,
                "constraints": {"min": 1, "max": 64},
            }
        ]
    return [
        {
            "name": "mode",
            "type": "text",
            "required": True,
            "constraints": {},
        }
    ]


DEFAULT_CATALOG: dict[str, Any] = {
    "version": 1,
    "steps": _make_default_steps(),
}


def ensure_default_models(fs: FileService) -> dict[str, bool]:
    """Compatibility shim that bootstraps only FlowConfig."""
    flow_cfg_status = ensure_flow_config_exists(fs)
    return {
        "catalog_created": False,
        "flow_created": False,
        "flow_config_created": flow_cfg_status["flow_config_created"],
    }
