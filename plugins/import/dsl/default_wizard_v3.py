"""Python-defined default WizardDefinition v3 for import CLI bootstrap.

ASCII-only.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_DEFAULT_WIZARD_DEFINITION_V3: dict[str, Any] = {
    "version": 3,
    "entry_step_id": "select_authors",
    "nodes": [
        {
            "step_id": "select_authors",
            "op": {
                "primitive_id": "ui.prompt_select",
                "primitive_version": 1,
                "inputs": {
                    "label": "Authors",
                    "prompt": "Select authors to import",
                    "help": (
                        "Enter a selector expression or JSON value. "
                        "Press Enter to accept the default all selector."
                    ),
                    "examples": ["all", "1", "1,2"],
                    "default_expr": {"expr": "$.state.vars.phase1.select_authors.selection_expr"},
                    "prefill_expr": {"expr": "$.state.vars.phase1.select_authors.selection_expr"},
                    "autofill_if": {"expr": "$.state.vars.phase1.select_authors.autofill_if"},
                },
                "writes": [
                    {
                        "to_path": "$.state.answers.select_authors.selection_expr",
                        "value": {"expr": "$.op.outputs.selection"},
                    }
                ],
            },
        },
        {
            "step_id": "select_books",
            "op": {
                "primitive_id": "ui.prompt_select",
                "primitive_version": 1,
                "inputs": {
                    "label": "Books",
                    "prompt": "Select books to import",
                    "help": (
                        "Enter a selector expression or JSON value. "
                        "Press Enter to accept the default all selector."
                    ),
                    "examples": ["all", "1", "1,2"],
                    "default_expr": {"expr": "$.state.vars.phase1.select_books.selection_expr"},
                    "prefill_expr": {"expr": "$.state.vars.phase1.select_books.selection_expr"},
                    "autofill_if": {"expr": "$.state.vars.phase1.select_books.autofill_if"},
                },
                "writes": [
                    {
                        "to_path": "$.state.answers.select_books.selection_expr",
                        "value": {"expr": "$.op.outputs.selection"},
                    }
                ],
            },
        },
        {
            "step_id": "plan_preview_batch",
            "op": {
                "primitive_id": "ui.message",
                "primitive_version": 1,
                "inputs": {
                    "text": (
                        "Preview the planned import batch before reviewing canonical "
                        "metadata and policy defaults."
                    )
                },
                "writes": [],
            },
        },
        {
            "step_id": "phase1_runtime_defaults",
            "op": {
                "primitive_id": "data.set",
                "primitive_version": 1,
                "inputs": {"value": {"expr": "$.state.vars.phase1.runtime"}},
                "writes": [
                    {
                        "to_path": "$.state.vars.phase1.runtime",
                        "value": {"expr": "$.op.outputs.value"},
                    }
                ],
            },
        },
        {
            "step_id": "effective_author_title",
            "op": {
                "primitive_id": "ui.prompt_text",
                "primitive_version": 1,
                "inputs": {
                    "label": "Effective author/title",
                    "prompt": "Review the canonical author/title payload",
                    "help": "Edit JSON to override the derived author/title values.",
                    "examples": [{"author": "Author A", "title": "Book A"}],
                    "default_expr": {"expr": "$.state.vars.phase1.runtime.effective_author_title"},
                    "prefill_expr": {"expr": "$.state.vars.phase1.runtime.effective_author_title"},
                },
                "writes": [
                    {
                        "to_path": "$.state.answers.effective_author_title",
                        "value": {"expr": "$.op.outputs.value"},
                    }
                ],
            },
        },
        {
            "step_id": "filename_policy",
            "op": {
                "primitive_id": "ui.prompt_text",
                "primitive_version": 1,
                "inputs": {
                    "label": "Filename policy",
                    "prompt": "Review the filename policy payload",
                    "help": "Edit JSON to override filename normalization defaults.",
                    "examples": [{"mode": "keep", "template": "{author}/{title}"}],
                    "default_expr": {"expr": "$.state.vars.phase1.runtime.filename_policy"},
                    "prefill_expr": {"expr": "$.state.vars.phase1.runtime.filename_policy"},
                },
                "writes": [
                    {
                        "to_path": "$.state.answers.filename_policy",
                        "value": {"expr": "$.op.outputs.value"},
                    }
                ],
            },
        },
        {
            "step_id": "covers_policy",
            "op": {
                "primitive_id": "ui.prompt_text",
                "primitive_version": 1,
                "inputs": {
                    "label": "Covers policy",
                    "prompt": "Review the covers policy payload",
                    "help": "Edit JSON to control embedded, skip, or URL-based cover handling.",
                    "examples": [
                        {"mode": "embedded", "url": ""},
                        {"mode": "skip", "url": ""},
                    ],
                    "default_expr": {"expr": "$.state.vars.phase1.runtime.covers_policy"},
                    "prefill_expr": {"expr": "$.state.vars.phase1.runtime.covers_policy"},
                },
                "writes": [
                    {
                        "to_path": "$.state.answers.covers_policy",
                        "value": {"expr": "$.op.outputs.value"},
                    }
                ],
            },
        },
        {
            "step_id": "id3_policy",
            "op": {
                "primitive_id": "ui.prompt_text",
                "primitive_version": 1,
                "inputs": {
                    "label": "ID3 policy",
                    "prompt": "Review the ID3 policy payload",
                    "help": "Edit JSON to override canonical metadata tags.",
                    "examples": [
                        {
                            "field_map": {"title": "title", "artist": "artist"},
                            "values": {"title": "Book A", "artist": "Author A"},
                        }
                    ],
                    "default_expr": {"expr": "$.state.vars.phase1.runtime.id3_policy"},
                    "prefill_expr": {"expr": "$.state.vars.phase1.runtime.id3_policy"},
                },
                "writes": [
                    {
                        "to_path": "$.state.answers.id3_policy",
                        "value": {"expr": "$.op.outputs.value"},
                    }
                ],
            },
        },
        {
            "step_id": "audio_processing",
            "op": {
                "primitive_id": "ui.prompt_text",
                "primitive_version": 1,
                "inputs": {
                    "label": "Audio processing",
                    "prompt": "Review the audio processing payload",
                    "help": "Edit JSON to override bitrate and processing flags.",
                    "examples": [{"bitrate": "128k", "loudnorm": False}],
                    "default_expr": {"expr": "$.state.vars.phase1.runtime.audio_processing"},
                    "prefill_expr": {"expr": "$.state.vars.phase1.runtime.audio_processing"},
                },
                "writes": [
                    {
                        "to_path": "$.state.answers.audio_processing",
                        "value": {"expr": "$.op.outputs.value"},
                    }
                ],
            },
        },
        {
            "step_id": "publish_policy",
            "op": {
                "primitive_id": "ui.prompt_text",
                "primitive_version": 1,
                "inputs": {
                    "label": "Publish policy",
                    "prompt": "Review the publish policy payload",
                    "help": "Edit JSON to override the deterministic target root.",
                    "examples": [{"target_root": "stage"}, {"target_root": "outbox"}],
                    "default_expr": {"expr": "$.state.vars.phase1.runtime.publish_policy"},
                    "prefill_expr": {"expr": "$.state.vars.phase1.runtime.publish_policy"},
                },
                "writes": [
                    {
                        "to_path": "$.state.answers.publish_policy",
                        "value": {"expr": "$.op.outputs.value"},
                    }
                ],
            },
        },
        {
            "step_id": "delete_source_policy",
            "op": {
                "primitive_id": "ui.prompt_text",
                "primitive_version": 1,
                "inputs": {
                    "label": "Delete source policy",
                    "prompt": "Review the delete-source policy payload",
                    "help": "Edit JSON to control clean-inbox behavior after publish.",
                    "examples": [{"enabled": False, "mode": "keep"}],
                    "default_expr": {"expr": "$.state.vars.phase1.runtime.delete_source_policy"},
                    "prefill_expr": {"expr": "$.state.vars.phase1.runtime.delete_source_policy"},
                },
                "writes": [
                    {
                        "to_path": "$.state.answers.delete_source_policy",
                        "value": {"expr": "$.op.outputs.value"},
                    }
                ],
            },
        },
        {
            "step_id": "conflict_policy",
            "op": {
                "primitive_id": "ui.prompt_select",
                "primitive_version": 1,
                "inputs": {
                    "label": "Conflict policy",
                    "prompt": "Choose how conflicts should be handled",
                    "help": "Select ask, skip, or overwrite for publish collisions.",
                    "examples": ["ask", "skip", "overwrite"],
                    "default_expr": {"expr": "$.state.vars.phase1.runtime.conflict_policy.mode"},
                    "prefill_expr": {"expr": "$.state.vars.phase1.runtime.conflict_policy.mode"},
                },
                "writes": [
                    {
                        "to_path": "$.state.answers.conflict_policy.mode",
                        "value": {"expr": "$.op.outputs.selection"},
                    }
                ],
            },
        },
        {
            "step_id": "parallelism",
            "op": {
                "primitive_id": "ui.prompt_text",
                "primitive_version": 1,
                "inputs": {
                    "label": "Parallelism",
                    "prompt": "Review the parallelism payload",
                    "help": "Edit JSON to control deterministic worker fan-out.",
                    "examples": [{"workers": 1}],
                    "default_expr": {"expr": "$.state.vars.phase1.runtime.parallelism"},
                    "prefill_expr": {"expr": "$.state.vars.phase1.runtime.parallelism"},
                },
                "writes": [
                    {
                        "to_path": "$.state.answers.parallelism",
                        "value": {"expr": "$.op.outputs.value"},
                    }
                ],
            },
        },
        {
            "step_id": "final_summary_confirm",
            "op": {
                "primitive_id": "ui.prompt_confirm",
                "primitive_version": 1,
                "inputs": {
                    "label": "Final summary",
                    "prompt": "Start processing with the canonical Phase 1 settings?",
                    "default_value": False,
                },
                "writes": [
                    {
                        "to_path": "$.state.answers.final_summary_confirm.confirm_start",
                        "value": {"expr": "$.op.outputs.confirmed"},
                    }
                ],
            },
        },
        {
            "step_id": "resolve_conflicts_batch",
            "op": {
                "primitive_id": "ui.prompt_confirm",
                "primitive_version": 1,
                "inputs": {
                    "label": "Resolve conflicts",
                    "prompt": "Conflicts were detected. Continue with the selected policy?",
                    "default_value": False,
                },
                "writes": [
                    {
                        "to_path": "$.state.answers.resolve_conflicts_batch.confirm",
                        "value": {"expr": "$.op.outputs.confirmed"},
                    }
                ],
            },
        },
        {
            "step_id": "processing",
            "op": {
                "primitive_id": "ctrl.stop",
                "primitive_version": 1,
                "inputs": {},
                "writes": [],
            },
        },
    ],
    "edges": [
        {"from": "select_authors", "to": "select_books"},
        {"from": "select_books", "to": "plan_preview_batch"},
        {"from": "plan_preview_batch", "to": "phase1_runtime_defaults"},
        {"from": "phase1_runtime_defaults", "to": "effective_author_title"},
        {"from": "effective_author_title", "to": "filename_policy"},
        {"from": "filename_policy", "to": "covers_policy"},
        {"from": "covers_policy", "to": "id3_policy"},
        {"from": "id3_policy", "to": "audio_processing"},
        {"from": "audio_processing", "to": "publish_policy"},
        {"from": "publish_policy", "to": "delete_source_policy"},
        {"from": "delete_source_policy", "to": "conflict_policy"},
        {"from": "conflict_policy", "to": "parallelism"},
        {"from": "parallelism", "to": "final_summary_confirm"},
        {
            "from": "final_summary_confirm",
            "to": "resolve_conflicts_batch",
            "condition_expr": {
                "expr": (
                    "$.state.answers.final_summary_confirm.confirm_start and "
                    "$.state.answers.conflict_policy.mode == 'ask' and "
                    "$.state.vars.phase1.runtime.resolve_conflicts_batch.has_conflicts"
                )
            },
        },
        {
            "from": "final_summary_confirm",
            "to": "processing",
            "condition_expr": {
                "expr": (
                    "$.state.answers.final_summary_confirm.confirm_start and not ("
                    "$.state.answers.conflict_policy.mode == 'ask' and "
                    "$.state.vars.phase1.runtime.resolve_conflicts_batch.has_conflicts"
                    ")"
                )
            },
        },
        {
            "from": "resolve_conflicts_batch",
            "to": "processing",
            "condition_expr": {"expr": "$.state.answers.resolve_conflicts_batch.confirm"},
        },
    ],
}


def build_default_wizard_definition_v3() -> dict[str, Any]:
    return deepcopy(_DEFAULT_WIZARD_DEFINITION_V3)


__all__ = ["build_default_wizard_definition_v3"]
