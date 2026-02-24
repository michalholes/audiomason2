"""Import plugin: StepCatalog (UI-only step metadata).

This is a read-only catalog used by UI editors.
It must be deterministic and ASCII-only.
"""

from __future__ import annotations

from typing import Any


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


# Single source of truth for UI-facing step metadata.
#
# Notes:
# - settings_schema + defaults_template are UI-only and do not affect runtime.
# - Keep descriptions short and deterministic.
STEP_CATALOG: dict[str, dict[str, Any]] = {
    "select_authors": {
        "title": "Select Authors",
        "description": "Choose authors to include in the import session.",
        "settings_schema": _schema([]),
        "defaults_template": {},
    },
    "select_books": {
        "title": "Select Books",
        "description": "Choose which books to import for the selected authors.",
        "settings_schema": _schema([]),
        "defaults_template": {},
    },
    "plan_preview_batch": {
        "title": "Plan Preview",
        "description": "Preview the planned operations before applying policies.",
        "settings_schema": _schema([]),
        "defaults_template": {},
    },
    "effective_author_title": {
        "title": "Effective Author Title",
        "description": "Show the effective author/title values computed for the plan.",
        "settings_schema": _schema([]),
        "defaults_template": {},
    },
    "filename_policy": {
        "title": "Filename Policy",
        "description": "Define filename normalization and naming behavior.",
        "settings_schema": _schema(
            [
                _field(key="hint", type_name="string", required=False, default=""),
            ]
        ),
        "defaults_template": {"hint": ""},
    },
    "covers_policy": {
        "title": "Covers Policy",
        "description": "Define how cover images are selected and applied.",
        "settings_schema": _schema(
            [
                _field(key="hint", type_name="string", required=False, default=""),
            ]
        ),
        "defaults_template": {"hint": ""},
    },
    "id3_policy": {
        "title": "ID3 Policy",
        "description": "Define how ID3 tags are written for audio outputs.",
        "settings_schema": _schema(
            [
                _field(key="hint", type_name="string", required=False, default=""),
            ]
        ),
        "defaults_template": {"hint": ""},
    },
    "audio_processing": {
        "title": "Audio Processing",
        "description": "Configure audio processing options used during import.",
        "settings_schema": _schema(
            [
                _field(key="hint", type_name="string", required=False, default=""),
            ]
        ),
        "defaults_template": {"hint": ""},
    },
    "publish_policy": {
        "title": "Publish Policy",
        "description": "Define how results are published after processing.",
        "settings_schema": _schema(
            [
                _field(key="hint", type_name="string", required=False, default=""),
            ]
        ),
        "defaults_template": {"hint": ""},
    },
    "delete_source_policy": {
        "title": "Delete Source Policy",
        "description": "Define whether and when source files may be deleted.",
        "settings_schema": _schema(
            [
                _field(key="hint", type_name="string", required=False, default=""),
            ]
        ),
        "defaults_template": {"hint": ""},
    },
    "conflict_policy": {
        "title": "Conflict Policy",
        "description": "Define conflict detection and resolution behavior.",
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
        "title": "Parallelism",
        "description": "Configure concurrency limits for processing jobs.",
        "settings_schema": _schema(
            [
                _field(key="max_jobs", type_name="int", required=False, default=0),
            ]
        ),
        "defaults_template": {"max_jobs": 0},
    },
    "final_summary_confirm": {
        "title": "Final Summary",
        "description": "Review the final plan summary and confirm execution.",
        "settings_schema": _schema([]),
        "defaults_template": {},
    },
    "resolve_conflicts_batch": {
        "title": "Resolve Conflicts",
        "description": "Resolve conflicts when conflict resolution is required.",
        "settings_schema": _schema([]),
        "defaults_template": {},
    },
    "processing": {
        "title": "Processing",
        "description": "Execute processing jobs and show progress.",
        "settings_schema": _schema([]),
        "defaults_template": {},
    },
}


def get_step_details(step_id: str) -> dict[str, Any] | None:
    """Return UI-only step details or None if unknown."""

    return STEP_CATALOG.get(step_id)
