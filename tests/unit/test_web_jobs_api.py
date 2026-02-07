from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from plugins.web_interface.core import WebInterfacePlugin


def _make_client(app: Any) -> Any:
    pytest.importorskip("httpx")  # required by fastapi/starlette TestClient
    from fastapi.testclient import TestClient

    return TestClient(app)


def test_web_jobs_api_create_list_cancel(tmp_path: Path, monkeypatch: Any) -> None:
    # Isolate HOME so jobs persist under tmp_path, not the real user home.
    monkeypatch.setenv("HOME", str(tmp_path))

    app = WebInterfacePlugin().create_app()
    client = _make_client(app)

    # Create a pending job (no execution).
    resp = client.post(
        "/api/jobs/process",
        json={"pipeline_path": "pipelines/example.yaml", "sources": ["a.mp3"]},
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    # List should include it.
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    assert any(it.get("job_id") == job_id for it in items)

    # Cancel should work from PENDING.
    resp = client.post(f"/api/jobs/{job_id}/cancel")
    assert resp.status_code == 200
    item = resp.json().get("item", {})
    assert item.get("state") == "cancelled"
