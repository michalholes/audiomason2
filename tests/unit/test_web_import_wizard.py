from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest


def _get_web_interface_plugin_cls() -> type:
    """Import the web_interface plugin in a pytest-collection-safe way."""

    repo_root = Path(__file__).resolve().parents[2]
    repo_root_s = str(repo_root)
    if repo_root_s not in sys.path:
        sys.path.insert(0, repo_root_s)

    from plugins.web_interface.core import WebInterfacePlugin

    return WebInterfacePlugin


def _make_client(app: Any) -> Any:
    pytest.importorskip("httpx")  # required by fastapi/starlette TestClient
    from fastapi.testclient import TestClient

    return TestClient(app)


def test_web_import_wizard_preflight_includes_book_only_group(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_INBOX_DIR", str(tmp_path / "inbox"))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_STAGE_DIR", str(tmp_path / "stage"))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_OUTBOX_DIR", str(tmp_path / "outbox"))

    (tmp_path / "inbox" / "AuthorA" / "BookA").mkdir(parents=True, exist_ok=True)
    (tmp_path / "inbox" / "AuthorA" / "BookA" / "a.mp3").write_bytes(b"dummy")
    (tmp_path / "inbox" / "BookOnly1").mkdir(parents=True, exist_ok=True)
    (tmp_path / "inbox" / "BookOnly1" / "b.mp3").write_bytes(b"dummy")

    web_interface_plugin_cls = _get_web_interface_plugin_cls()
    app = web_interface_plugin_cls().create_app()
    client = _make_client(app)

    resp = client.post("/api/import_wizard/preflight", json={"root": "inbox", "path": "."})
    assert resp.status_code == 200
    data = resp.json()

    authors = data.get("authors", [])
    assert "AuthorA" in authors
    assert "<book-only>" in authors

    books = data.get("books", [])
    assert any((b.get("author") == "" and b.get("book") == "BookOnly1") for b in books)


def test_web_import_wizard_start_creates_jobs_and_validates(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_INBOX_DIR", str(tmp_path / "inbox"))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_STAGE_DIR", str(tmp_path / "stage"))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_OUTBOX_DIR", str(tmp_path / "outbox"))

    (tmp_path / "inbox" / "BookOnly1").mkdir(parents=True, exist_ok=True)
    (tmp_path / "inbox" / "BookOnly1" / "b.mp3").write_bytes(b"dummy")

    web_interface_plugin_cls = _get_web_interface_plugin_cls()
    app = web_interface_plugin_cls().create_app()
    client = _make_client(app)

    # Start should return job ids (no 500).
    resp = client.post(
        "/api/import_wizard/start",
        json={"root": "inbox", "path": ".", "book_rel_path": "BookOnly1", "mode": "stage"},
    )
    assert resp.status_code == 200
    job_ids = resp.json().get("job_ids", [])
    assert isinstance(job_ids, list)
    assert len(job_ids) == 1
    assert isinstance(job_ids[0], str) and job_ids[0]

    # Validation errors should be 400 with a message.
    resp = client.post("/api/import_wizard/start", json={"book_rel_path": "BookOnly1"})
    assert resp.status_code == 400
    assert "root" in str(resp.json().get("detail"))


def test_web_ui_schema_has_import_nav_entry(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    web_interface_plugin_cls = _get_web_interface_plugin_cls()
    app = web_interface_plugin_cls().create_app()
    client = _make_client(app)

    resp = client.get("/api/ui/nav")
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    assert any(
        (it.get("route") == "/import" and it.get("page_id") == "import_wizard") for it in items
    )
