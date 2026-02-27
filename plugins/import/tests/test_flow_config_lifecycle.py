from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from plugins.file_io.service import FileService  # noqa: E402
from plugins.file_io.service.types import RootName  # noqa: E402


def _mod(name: str):
    return importlib.import_module(name)


editor_storage = _mod("plugins.import.editor_storage")
fingerprints = _mod("plugins.import.fingerprints")


def _fs(tmp_path: Path) -> FileService:
    return FileService({RootName.WIZARDS: tmp_path})


def test_flow_config_get_returns_active_when_no_draft(tmp_path: Path) -> None:
    fs = _fs(tmp_path)

    active = editor_storage.ensure_flow_config_active_exists(fs)
    got = editor_storage.get_flow_config_draft(fs)

    assert got == active
    assert fs.exists(RootName.WIZARDS, editor_storage.FLOW_CONFIG_REL_PATH)
    assert not fs.exists(RootName.WIZARDS, editor_storage.FLOW_CONFIG_DRAFT_REL_PATH)


def test_flow_config_activate_requires_draft(tmp_path: Path) -> None:
    fs = _fs(tmp_path)

    editor_storage.ensure_flow_config_active_exists(fs)
    with pytest.raises(ValueError):
        editor_storage.activate_flow_config_draft(fs)


def test_flow_config_activate_snapshots_history_and_deletes_draft(tmp_path: Path) -> None:
    fs = _fs(tmp_path)

    active0 = editor_storage.ensure_flow_config_active_exists(fs)
    fp0 = fingerprints.fingerprint_json(active0)

    draft = {
        "version": 1,
        "steps": {"optional_step": {"enabled": True}},
        "defaults": {},
    }
    editor_storage.put_flow_config_draft(fs, draft)

    active1 = editor_storage.activate_flow_config_draft(fs)

    assert active1["steps"]["optional_step"]["enabled"] is True
    assert not fs.exists(RootName.WIZARDS, editor_storage.FLOW_CONFIG_DRAFT_REL_PATH)

    index_path = "import/editor_history/flow_config/index.json"
    assert fs.exists(RootName.WIZARDS, index_path)

    with fs.open_read(RootName.WIZARDS, index_path) as f:
        data = f.read().decode("utf-8")
    assert fp0 in data
