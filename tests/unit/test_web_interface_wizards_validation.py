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


def _set_roots(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_INBOX_DIR", str(tmp_path / "inbox"))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_STAGE_DIR", str(tmp_path / "stage"))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_OUTBOX_DIR", str(tmp_path / "outbox"))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_WIZARDS_DIR", str(tmp_path / "wizards"))


def test_wizard_validate_rejects_duplicate_step_ids(tmp_path: Path, monkeypatch: Any) -> None:
    _set_roots(monkeypatch, tmp_path)

    app = _get_web_interface_plugin_cls()().create_app()
    client = _make_client(app)

    model = {
        "wizard": {
            "name": "W",
            "description": "",
            "steps": [
                {"id": "a", "type": "input", "prompt": "x"},
                {"id": "a", "type": "input", "prompt": "y"},
            ],
        }
    }

    resp = client.post("/api/wizards/validate", json={"model": model})
    assert resp.status_code == 400
    assert "duplicate" in resp.json().get("detail", "").lower()


def test_wizard_validate_accepts_templates_and_defaults_memory(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _set_roots(monkeypatch, tmp_path)

    app = _get_web_interface_plugin_cls()().create_app()
    client = _make_client(app)

    model = {
        "wizard": {
            "name": "W",
            "description": "",
            "_ui": {
                "defaults_memory": {"author": "Unknown"},
                "templates": {"basic_input": {"type": "input", "prompt": "P"}},
            },
            "steps": [
                {
                    "id": "author",
                    "type": "input",
                    "enabled": True,
                    "template": "basic_input",
                    "defaults": {"fallback": "Unknown"},
                    "when": {"op": "exists", "path": "preflight.author"},
                }
            ],
        }
    }

    resp = client.post("/api/wizards/validate", json={"model": model})
    assert resp.status_code == 200
    j = resp.json()
    assert j.get("ok") is True
    assert "wizard" in (j.get("model") or {})
    assert isinstance(j.get("yaml"), str) and j.get("yaml")
