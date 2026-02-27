from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))


def _mod(name: str):
    return importlib.import_module(name)


flow_v = _mod("plugins.import.flow_config_validation")
wd_storage = _mod("plugins.import.wizard_editor_storage")
errors_mod = _mod("plugins.import.errors")
FinalizeError = errors_mod.FinalizeError


def test_flow_config_rejects_ui_key() -> None:
    with pytest.raises(ValueError):
        flow_v.normalize_flow_config({"version": 1, "steps": {}, "defaults": {}, "ui": {"x": 1}})


def test_wizard_definition_v2_rejects_wizard_id() -> None:
    bad = {
        "version": 2,
        "wizard_id": "import",
        "graph": {
            "entry_step_id": "select_authors",
            "nodes": [{"step_id": "select_authors"}],
            "edges": [],
        },
    }
    with pytest.raises(FinalizeError):
        wd_storage.canonicalize_to_v2(bad)


def test_wizard_definition_v2_rejects_unknown_keys() -> None:
    bad = {
        "version": 2,
        "graph": {
            "entry_step_id": "select_authors",
            "nodes": [{"step_id": "select_authors", "extra": 1}],
            "edges": [],
        },
    }
    with pytest.raises(FinalizeError):
        wd_storage.canonicalize_to_v2(bad)
