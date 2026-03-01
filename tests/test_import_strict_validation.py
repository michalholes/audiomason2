"""Issue 270: strict validators for FlowConfig and WizardDefinition."""

from __future__ import annotations

from importlib import import_module

import pytest

normalize_flow_config = import_module("plugins.import.flow_config_validation").normalize_flow_config
FinalizeError = import_module("plugins.import.errors").FinalizeError
validate_wizard_definition_structure = import_module(
    "plugins.import.wizard_definition_model"
).validate_wizard_definition_structure


def test_flow_config_rejects_ui() -> None:
    with pytest.raises(ValueError):
        normalize_flow_config({"version": 1, "steps": {}, "defaults": {}, "ui": {}})


def test_wizard_definition_v2_rejects_wizard_id() -> None:
    with pytest.raises(FinalizeError):
        validate_wizard_definition_structure(
            {
                "version": 2,
                "wizard_id": "import",
                "graph": {
                    "entry_step_id": "select_authors",
                    "nodes": [{"step_id": "select_authors"}],
                    "edges": [],
                },
            }
        )


def test_wizard_definition_v2_rejects_unknown_keys() -> None:
    with pytest.raises(FinalizeError):
        validate_wizard_definition_structure(
            {
                "version": 2,
                "graph": {
                    "entry_step_id": "select_authors",
                    "nodes": [{"step_id": "select_authors", "extra": 1}],
                    "edges": [],
                },
            }
        )

    with pytest.raises(FinalizeError):
        validate_wizard_definition_structure(
            {
                "version": 2,
                "graph": {
                    "entry_step_id": "select_authors",
                    "nodes": [{"step_id": "select_authors"}],
                    "edges": [
                        {
                            "from_step_id": "select_authors",
                            "to_step_id": "select_authors",
                            "priority": 1,
                            "when": None,
                            "x": 1,
                        }
                    ],
                },
            }
        )


def test_wizard_definition_v2_rejects_editor_metadata() -> None:
    with pytest.raises(FinalizeError):
        validate_wizard_definition_structure(
            {
                "version": 2,
                "graph": {
                    "entry_step_id": "select_authors",
                    "nodes": [{"step_id": "select_authors"}],
                    "edges": [],
                },
                "_am2_ui": {"showOptional": True},
            }
        )
