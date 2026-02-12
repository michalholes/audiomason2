from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest


def _get_web_interface_plugin_cls() -> type:
    repo_root = Path(__file__).resolve().parents[2]
    repo_root_s = str(repo_root)
    if repo_root_s not in sys.path:
        sys.path.insert(0, repo_root_s)

    from plugins.web_interface.core import WebInterfacePlugin

    return WebInterfacePlugin


def _make_client(app: Any) -> Any:
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    return TestClient(app)


def _set_roots(monkeypatch: Any, tmp_path: Path) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_INBOX_DIR", str(tmp_path / "inbox"))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_STAGE_DIR", str(tmp_path / "stage"))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_OUTBOX_DIR", str(tmp_path / "outbox"))
    wizards_dir = tmp_path / "wizards"
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_WIZARDS_DIR", str(wizards_dir))
    return wizards_dir


def test_wizard_get_parses_steps_missing_id_and_type(tmp_path: Path, monkeypatch: Any) -> None:
    wizards_dir = _set_roots(monkeypatch, tmp_path)
    (wizards_dir / "definitions").mkdir(parents=True, exist_ok=True)

    # Legacy-ish wizard: steps entries without id/type.
    (wizards_dir / "definitions" / "legacy.yaml").write_text(
        "wizard:\n  name: Legacy\n  steps:\n    - prompt: 'Hello'\n",
        encoding="ascii",
    )

    app = _get_web_interface_plugin_cls()().create_app()
    client = _make_client(app)

    resp = client.get("/api/wizards/legacy")
    assert resp.status_code == 200
    model = resp.json().get("model", {})
    steps = ((model or {}).get("wizard") or {}).get("steps") or []
    assert len(steps) == 1
    assert steps[0].get("id") == "step_1"
    assert steps[0].get("type") == "unknown"


def test_wizard_put_rejects_invalid_yaml(tmp_path: Path, monkeypatch: Any) -> None:
    _set_roots(monkeypatch, tmp_path)
    app = _get_web_interface_plugin_cls()().create_app()
    client = _make_client(app)

    # YAML without top-level wizard mapping is invalid for safe save.
    resp = client.put("/api/wizards/bad", json={"yaml": "steps: []\n"})
    assert resp.status_code == 400
