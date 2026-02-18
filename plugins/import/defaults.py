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
        "resolve_conflicts_batch",
        "final_summary_confirm",
    ]

    steps: list[dict[str, Any]] = []
    for step_id in required_order:
        steps.append(
            {
                "step_id": step_id,
                "message_id": f"{step_id}.title",
                "default_text": step_id.replace("_", " ").title(),
                "fields": {},
                "allowed_actions": ["back", "next"],
                "validation": [],
                "state_effects": [],
            }
        )

    # The first step cannot go "back" to anything meaningful, but leaving "back"
    # enabled is harmless in the engine (it will resolve to None and be rejected
    # by the flow node map). Keep it consistent with other steps.
    return steps


DEFAULT_CATALOG: dict[str, Any] = {
    "version": 1,
    "steps": _make_default_steps(),
}

DEFAULT_FLOW: dict[str, Any] = {
    "version": 1,
    "entry_step_id": "select_authors",
    "nodes": [s["step_id"] for s in DEFAULT_CATALOG["steps"]],
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
    return {"catalog_created": catalog_created, "flow_created": flow_created}
