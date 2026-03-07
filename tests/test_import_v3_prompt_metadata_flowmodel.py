"""Issue 108: FlowModel prompt metadata projection and step API normalization."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from audiomason.core.config import ConfigResolver

ImportWizardEngine = import_module("plugins.import.engine").ImportWizardEngine
atomic_write_json = import_module("plugins.import.storage").atomic_write_json
RootName = import_module("plugins.file_io.service.types").RootName
WIZARD_DEFINITION_REL_PATH = import_module(
    "plugins.import.wizard_definition_model"
).WIZARD_DEFINITION_REL_PATH


PROMPT_METADATA_FLOW = {
    "version": 3,
    "entry_step_id": "seed_name",
    "nodes": [
        {
            "step_id": "seed_name",
            "op": {
                "primitive_id": "data.set",
                "primitive_version": 1,
                "inputs": {"value": "Ada"},
                "writes": [
                    {
                        "to_path": "$.state.vars.seed_name",
                        "value": {"expr": "$.op.outputs.value"},
                    }
                ],
            },
        },
        {
            "step_id": "seed_flag",
            "op": {
                "primitive_id": "data.set",
                "primitive_version": 1,
                "inputs": {"value": False},
                "writes": [
                    {
                        "to_path": "$.state.vars.should_autofill",
                        "value": {"expr": "$.op.outputs.value"},
                    }
                ],
            },
        },
        {
            "step_id": "ask_name",
            "op": {
                "primitive_id": "ui.prompt_text",
                "primitive_version": 1,
                "inputs": {
                    "label": "Name",
                    "prompt": "Enter the normalized name",
                    "help": "Used by the renderer",
                    "default_value": "fallback",
                    "prefill": "literal",
                    "default_expr": {"expr": "$.state.vars.seed_name"},
                    "prefill_expr": {"expr": "$.state.vars.seed_name"},
                    "autofill_if": {"expr": "$.state.vars.should_autofill"},
                },
                "writes": [
                    {
                        "to_path": "$.state.answers.ask_name.value",
                        "value": {"expr": "$.op.outputs.value"},
                    }
                ],
            },
        },
        {
            "step_id": "stop",
            "op": {
                "primitive_id": "ctrl.stop",
                "primitive_version": 1,
                "inputs": {},
                "writes": [],
            },
        },
    ],
    "edges": [
        {"from": "seed_name", "to": "seed_flag"},
        {"from": "seed_flag", "to": "ask_name"},
        {"from": "ask_name", "to": "stop"},
    ],
}


def _make_engine(tmp_path: Path) -> ImportWizardEngine:
    roots = {
        "inbox": tmp_path / "inbox",
        "stage": tmp_path / "stage",
        "outbox": tmp_path / "outbox",
        "jobs": tmp_path / "jobs",
        "config": tmp_path / "config",
        "wizards": tmp_path / "wizards",
    }
    for root in roots.values():
        root.mkdir(parents=True, exist_ok=True)
    defaults = {
        "file_io": {
            "roots": {
                "inbox_dir": str(roots["inbox"]),
                "stage_dir": str(roots["stage"]),
                "outbox_dir": str(roots["outbox"]),
                "jobs_dir": str(roots["jobs"]),
                "config_dir": str(roots["config"]),
                "wizards_dir": str(roots["wizards"]),
            }
        },
        "output_dir": str(roots["outbox"]),
        "diagnostics": {"enabled": False},
    }
    resolver = ConfigResolver(
        cli_args=defaults,
        defaults=defaults,
        user_config_path=tmp_path / "no_user_config.yaml",
        system_config_path=tmp_path / "no_system_config.yaml",
    )
    return ImportWizardEngine(resolver=resolver)


def test_flow_model_projects_prompt_ui_and_step_api_normalizes_current_step(
    tmp_path: Path,
) -> None:
    engine = _make_engine(tmp_path)
    fs = engine.get_file_service()
    atomic_write_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH, PROMPT_METADATA_FLOW)

    flow_model = engine.get_flow_model()
    steps = {step["step_id"]: step for step in flow_model["steps"]}

    assert steps["ask_name"]["ui"] == {
        "label": "Name",
        "prompt": "Enter the normalized name",
        "help": "Used by the renderer",
        "default_value": "fallback",
        "prefill": "literal",
        "default_expr": {"expr": "$.state.vars.seed_name"},
        "prefill_expr": {"expr": "$.state.vars.seed_name"},
        "autofill_if": {"expr": "$.state.vars.should_autofill"},
    }
    assert "ui" not in steps["seed_name"]
    assert "ui" not in steps["stop"]

    state = engine.create_session("inbox", "")
    assert state["status"] == "in_progress"
    assert state["current_step_id"] == "ask_name"

    step = engine.get_step_definition(state["session_id"], "ask_name")

    assert step["ui"] == {
        "label": "Name",
        "prompt": "Enter the normalized name",
        "help": "Used by the renderer",
        "default_value": "Ada",
        "prefill": "Ada",
        "autofill_if": False,
    }
