"""Issue 190: import UI step projection route regression coverage."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from audiomason.core.config import ConfigResolver

ImportWizardEngine = import_module("plugins.import.engine").ImportWizardEngine
build_router = import_module("plugins.import.ui_api").build_router

_HAS_FASTAPI = True
try:
    import fastapi  # noqa: F401
except Exception:
    _HAS_FASTAPI = False

try:
    import httpx  # noqa: F401

    _HAS_HTTPX = True
except Exception:
    _HAS_HTTPX = False


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


def _write_inbox_tree(tmp_path: Path) -> None:
    for rel_path, content in (
        ("A/Book1/a.txt", "x"),
        ("A/Book2/b.txt", "y"),
        ("B/Book3/c.txt", "z"),
    ):
        path = tmp_path / "inbox" / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


@pytest.mark.skipif((not _HAS_FASTAPI) or (not _HAS_HTTPX), reason="fastapi+httpx required")
def test_import_ui_step_projection_route_returns_runtime_author_items(
    tmp_path: Path,
) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    engine = _make_engine(tmp_path)
    _write_inbox_tree(tmp_path)

    app = FastAPI()
    app.include_router(build_router(engine=engine))
    client = TestClient(app)

    state = engine.create_session("inbox", "", mode="stage")
    session_id = str(state["session_id"])
    response = client.get(f"/import/ui/session/{session_id}/step/select_authors")

    assert response.status_code == 200
    payload = response.json()
    assert payload["step_id"] == "select_authors"
    assert payload["primitive_id"] == "ui.prompt_select"
    assert payload["ui"]["items"]
    assert [item["display_label"] for item in payload["ui"]["items"]] == ["A", "B"]


@pytest.mark.skipif((not _HAS_FASTAPI) or (not _HAS_HTTPX), reason="fastapi+httpx required")
def test_import_ui_step_projection_route_returns_scoped_book_items(
    tmp_path: Path,
) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    engine = _make_engine(tmp_path)
    _write_inbox_tree(tmp_path)

    app = FastAPI()
    app.include_router(build_router(engine=engine))
    client = TestClient(app)

    state = engine.create_session("inbox", "A", mode="stage")
    session_id = str(state["session_id"])
    response = client.get(f"/import/ui/session/{session_id}/step/select_books")

    assert response.status_code == 200
    payload = response.json()
    assert payload["step_id"] == "select_books"
    assert payload["primitive_id"] == "ui.prompt_select"
    assert [item["display_label"] for item in payload["ui"]["items"]] == [
        "A / Book1",
        "A / Book2",
    ]
