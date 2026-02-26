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
    """Return UI-only step details or None if unknown."""

    return STEP_CATALOG.get(step_id)
