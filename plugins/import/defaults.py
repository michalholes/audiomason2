"""Default wizard models for the import plugin.

These defaults are used to bootstrap catalog/catalog.json and flow/current.json
under the WIZARDS root when they do not exist yet.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from plugins.file_io.service import FileService, RootName

from .models import CatalogModel, FlowModel, validate_models
from .storage import atomic_write_json_if_missing


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
        "conflict_policy",
        "parallelism",
        "final_summary_confirm",
        "resolve_conflicts_batch",
    ]

    steps: list[dict[str, Any]] = []
    for step_id in required_order:
        computed_only = step_id in {"plan_preview_batch"}
        steps.append(
            {
                "step_id": step_id,
                "title": step_id.replace("_", " ").title(),
                "computed_only": computed_only,
                "fields": _default_fields_for_step(step_id),
            }
        )

    # The first step cannot go "back" to anything meaningful, but leaving "back"
    # enabled is harmless in the engine (it will resolve to None and be rejected
    # by the flow node map). Keep it consistent with other steps.
    return steps


def _default_fields_for_step(step_id: str) -> list[dict[str, Any]]:
    # Field schemas are intentionally minimal but strict.
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
    if step_id == "plan_preview_batch":
        return []
    if step_id == "final_summary_confirm":
        return [
            {
                "name": "confirm",
                "type": "confirm",
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
    # Generic policy steps accept a single string mode.
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

DEFAULT_FLOW: dict[str, Any] = {
    "version": 1,
    "entry_step_id": "select_authors",
    "nodes": [
        {
            "step_id": "select_authors",
            "next_step_id": "select_books",
            "prev_step_id": None,
        },
        {
            "step_id": "select_books",
            "next_step_id": "plan_preview_batch",
            "prev_step_id": "select_authors",
        },
        {
            "step_id": "plan_preview_batch",
            "next_step_id": "effective_author_title",
            "prev_step_id": "select_books",
        },
        {
            "step_id": "effective_author_title",
            "next_step_id": "filename_policy",
            "prev_step_id": "plan_preview_batch",
        },
        {
            "step_id": "filename_policy",
            "next_step_id": "covers_policy",
            "prev_step_id": "effective_author_title",
        },
        {
            "step_id": "covers_policy",
            "next_step_id": "id3_policy",
            "prev_step_id": "filename_policy",
        },
        {
            "step_id": "id3_policy",
            "next_step_id": "audio_processing",
            "prev_step_id": "covers_policy",
        },
        {
            "step_id": "audio_processing",
            "next_step_id": "publish_policy",
            "prev_step_id": "id3_policy",
        },
        {
            "step_id": "publish_policy",
            "next_step_id": "delete_source_policy",
            "prev_step_id": "audio_processing",
        },
        {
            "step_id": "delete_source_policy",
            "next_step_id": "conflict_policy",
            "prev_step_id": "publish_policy",
        },
        {
            "step_id": "conflict_policy",
            "next_step_id": "parallelism",
            "prev_step_id": "delete_source_policy",
        },
        {
            "step_id": "parallelism",
            "next_step_id": "final_summary_confirm",
            "prev_step_id": "conflict_policy",
        },
        {
            "step_id": "final_summary_confirm",
            "next_step_id": None,
            "prev_step_id": "parallelism",
        },
        {
            # Exists but not linked by default; engine may jump to it conditionally.
            "step_id": "resolve_conflicts_batch",
            "next_step_id": None,
            "prev_step_id": "final_summary_confirm",
        },
    ],
}


# FlowConfig stores user overrides only. It must not modify the catalog or base flow definition.
DEFAULT_FLOW_CONFIG: dict[str, Any] = {
    "version": 1,
    "overrides": {},
}


def ensure_default_models(fs: FileService) -> dict[str, bool]:
    """Ensure wizard model JSON files exist; create them if missing.

    Returns dict with keys:
      - catalog_created
      - flow_created
    """
    # Validate defaults in-memory so we never write an invalid model.
    catalog = CatalogModel.from_dict(DEFAULT_CATALOG)
    flow = FlowModel.from_dict(DEFAULT_FLOW)
    validate_models(catalog, flow)

    catalog_created = atomic_write_json_if_missing(
        fs, RootName.WIZARDS, "import/catalog/catalog.json", DEFAULT_CATALOG
    )
    flow_created = atomic_write_json_if_missing(
        fs, RootName.WIZARDS, "import/flow/current.json", DEFAULT_FLOW
    )

    flow_config_created = atomic_write_json_if_missing(
        fs, RootName.WIZARDS, "import/config/flow_config.json", DEFAULT_FLOW_CONFIG
    )
    return {
        "catalog_created": catalog_created,
        "flow_created": flow_created,
        "flow_config_created": flow_config_created,
    }
