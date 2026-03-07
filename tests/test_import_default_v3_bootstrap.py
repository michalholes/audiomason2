"""Issue 111: targeted v3 default bootstrap for new CLI import sessions."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from audiomason.core.config import ConfigResolver

ImportWizardEngine = import_module("plugins.import.engine").ImportWizardEngine
atomic_write_json = import_module("plugins.import.storage").atomic_write_json
canonicalize_wizard_definition = import_module(
    "plugins.import.wizard_definition_model"
).canonicalize_wizard_definition
load_or_bootstrap_wizard_definition = import_module(
    "plugins.import.wizard_definition_model"
).load_or_bootstrap_wizard_definition
RootName = import_module("plugins.file_io.service.types").RootName
WIZARD_DEFINITION_REL_PATH = import_module(
    "plugins.import.wizard_definition_model"
).WIZARD_DEFINITION_REL_PATH


def _make_engine(tmp_path: Path) -> ImportWizardEngine:
    roots = {
        name: tmp_path / name for name in ("inbox", "stage", "outbox", "jobs", "config", "wizards")
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


def test_load_or_bootstrap_can_create_python_defined_v3_default(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    fs = engine.get_file_service()

    out = load_or_bootstrap_wizard_definition(fs, bootstrap_default_version=3)

    assert out == canonicalize_wizard_definition(out)
    assert out["version"] == 3
    assert out["entry_step_id"] == "select_authors"
    assert [node["step_id"] for node in out["nodes"]] == [
        "conflict_policy",
        "final_summary_confirm",
        "plan_preview_batch",
        "processing",
        "select_authors",
        "select_books",
    ]


def test_load_or_bootstrap_replaces_invalid_artifact_with_v3_default(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    fs = engine.get_file_service()
    atomic_write_json(
        fs,
        RootName.WIZARDS,
        WIZARD_DEFINITION_REL_PATH,
        {"version": 3, "entry_step_id": "Bad.Step", "nodes": [], "edges": []},
    )

    out = load_or_bootstrap_wizard_definition(fs, bootstrap_default_version=3)

    assert out == canonicalize_wizard_definition(out)
    assert out["version"] == 3
