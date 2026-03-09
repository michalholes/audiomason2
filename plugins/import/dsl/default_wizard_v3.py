"""Python-defined default WizardDefinition v3 for import CLI bootstrap.

ASCII-only.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

DEFAULT_WIZARD_DEFINITION_V3: dict[str, Any] = {
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
                        "Preview the planned import batch before choosing the conflict policy."
                    )
                },
                "writes": [],
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
                    "examples": ["ask", "skip", "overwrite"],
                    "default_expr": {"expr": "$.state.vars.phase1.policy.conflict_policy.mode"},
                    "prefill_expr": {"expr": "$.state.vars.phase1.policy.conflict_policy.mode"},
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
            "step_id": "final_summary_confirm",
            "op": {
                "primitive_id": "ui.prompt_confirm",
                "primitive_version": 1,
                "inputs": {
                    "label": "Final summary",
                    "prompt": "Start processing with the selected import settings?",
                    "default_value": False,
                },
                "writes": [
                    {
                        "to_path": ("$.state.answers.final_summary_confirm.confirm_start"),
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
        {"from": "plan_preview_batch", "to": "conflict_policy"},
        {"from": "conflict_policy", "to": "final_summary_confirm"},
        {
            "from": "final_summary_confirm",
            "to": "processing",
            "condition_expr": {"expr": "$.state.answers.final_summary_confirm.confirm_start"},
        },
    ],
}


def build_default_wizard_definition_v3() -> dict[str, Any]:
    return deepcopy(DEFAULT_WIZARD_DEFINITION_V3)


__all__ = ["DEFAULT_WIZARD_DEFINITION_V3", "build_default_wizard_definition_v3"]
