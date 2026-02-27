from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from plugins.file_io.service import FileService  # noqa: E402
from plugins.file_io.service.types import RootName  # noqa: E402


def _mod(name: str):
    return importlib.import_module(name)


fingerprints = _mod("plugins.import.fingerprints")
storage = _mod("plugins.import.wizard_editor_storage")
wd_model = _mod("plugins.import.wizard_definition_model")


def _fs(tmp_path: Path) -> FileService:
    return FileService({RootName.WIZARDS: tmp_path})


def test_wizard_definition_get_returns_active_when_no_draft(tmp_path: Path) -> None:
    fs = _fs(tmp_path)

    active = storage.ensure_wizard_definition_active_exists(fs)
    got = storage.get_wizard_definition_draft(fs)

    assert got == active
    assert not fs.exists(RootName.WIZARDS, storage.WIZARD_DEFINITION_DRAFT_REL_PATH)


def test_wizard_definition_activate_snapshots_history_when_changed(tmp_path: Path) -> None:
    fs = _fs(tmp_path)

    active0 = storage.ensure_wizard_definition_active_exists(fs)
    fp0 = fingerprints.fingerprint_json(active0)

    draft = dict(wd_model.DEFAULT_WIZARD_DEFINITION)
    graph = dict(draft.get("graph") or {})
    nodes = list(graph.get("nodes") or [])
    if len(nodes) >= 2:
        nodes[0], nodes[1] = nodes[1], nodes[0]
    graph["nodes"] = nodes
    draft["graph"] = graph

    storage.put_wizard_definition_draft(fs, draft)
    active1 = storage.activate_wizard_definition_draft(fs)

    assert active1.get("version") == 2
    assert not fs.exists(RootName.WIZARDS, storage.WIZARD_DEFINITION_DRAFT_REL_PATH)

    index_path = "import/editor_history/wizard_definition/index.json"
    assert fs.exists(RootName.WIZARDS, index_path)

    with fs.open_read(RootName.WIZARDS, index_path) as f:
        data = f.read().decode("utf-8")
    assert fp0 in data
