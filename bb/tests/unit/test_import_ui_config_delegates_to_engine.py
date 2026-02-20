"""Issue 220: import UI config routes must delegate to engine APIs."""

from __future__ import annotations

from importlib import import_module

import pytest

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


class _DummyEngine:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def get_flow_model(self):
        self.calls.append(("get_flow_model", None))
        return {"ok": True}

    def get_flow_config(self):
        self.calls.append(("get_flow_config", None))
        return {"version": 1, "steps": {}}

    def set_flow_config(self, body):
        self.calls.append(("set_flow_config", body))
        return {"version": 1, "steps": {"x": {"enabled": True}}}

    def reset_flow_config(self):
        self.calls.append(("reset_flow_config", None))
        return {"version": 1, "steps": {}}


@pytest.mark.skipif((not _HAS_FASTAPI) or (not _HAS_HTTPX), reason="fastapi+httpx required")
def test_ui_config_endpoints_call_engine_methods_only() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    engine = _DummyEngine()
    app = FastAPI()
    app.include_router(build_router(engine=engine))
    client = TestClient(app)

    r1 = client.get("/import/ui/config")
    assert r1.status_code == 200
    assert r1.json()["version"] == 1

    r2 = client.post("/import/ui/config", json={"version": 1, "steps": {"x": {"enabled": True}}})
    assert r2.status_code == 200

    r3 = client.post("/import/ui/config/reset", json={})
    assert r3.status_code == 200

    assert [c[0] for c in engine.calls] == [
        "get_flow_config",
        "set_flow_config",
        "reset_flow_config",
    ]
