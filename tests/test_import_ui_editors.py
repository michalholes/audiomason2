"""Issue 240: FlowConfig and WizardDefinition editors (history/rollback)."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from audiomason.core.config import ConfigResolver

fingerprint_json = import_module("plugins.import.fingerprints").fingerprint_json
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
        "inbox": tmp_path / "inbox",
        "stage": tmp_path / "stage",
        "outbox": tmp_path / "outbox",
        "jobs": tmp_path / "jobs",
        "config": tmp_path / "config",
        "wizards": tmp_path / "wizards",
    }
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


@pytest.mark.skipif((not _HAS_FASTAPI) or (not _HAS_HTTPX), reason="fastapi+httpx required")
def test_flow_config_validate_does_not_persist(tmp_path: Path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    engine = _make_engine(tmp_path)
    app = FastAPI()
    app.include_router(build_router(engine=engine))
    client = TestClient(app)

    base = client.get("/import/ui/config").json()["config"]
    changed = dict(base)
    changed["defaults"] = {"marker": 1}

    r = client.post("/import/ui/config/validate", json={"config": changed})
    assert r.status_code == 200
    out = r.json()["config"]
    assert (out.get("defaults") or {}).get("marker") == 1

    after = client.get("/import/ui/config").json()["config"]
    assert (after.get("defaults") or {}).get("marker") != 1


@pytest.mark.skipif((not _HAS_FASTAPI) or (not _HAS_HTTPX), reason="fastapi+httpx required")
def test_flow_config_history_and_rollback(tmp_path: Path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    engine = _make_engine(tmp_path)
    app = FastAPI()
    app.include_router(build_router(engine=engine))
    client = TestClient(app)

    base = client.post("/import/ui/config/reset", json={}).json()["config"]
    cfg1 = dict(base)
    cfg1["defaults"] = {"marker": 1}
    cfg2 = dict(base)
    cfg2["defaults"] = {"marker": 2}

    assert client.post("/import/ui/config", json={"config": cfg1}).status_code == 200
    assert client.post("/import/ui/config/activate", json={}).status_code == 200
    assert client.post("/import/ui/config", json={"config": cfg2}).status_code == 200
    assert client.post("/import/ui/config/activate", json={}).status_code == 200

    hist = client.get("/import/ui/config/history").json()["items"]
    ids = [it["id"] for it in hist]
    assert fingerprint_json(cfg1) in set(ids)

    rid = fingerprint_json(cfg1)
    rb = client.post("/import/ui/config/rollback", json={"id": rid})
    assert rb.status_code == 200
    cur = rb.json()["config"]
    assert (cur.get("defaults") or {}).get("marker") == 1

    nf = client.post("/import/ui/config/rollback", json={"id": "nope"})
    assert nf.status_code == 404


@pytest.mark.skipif((not _HAS_FASTAPI) or (not _HAS_HTTPX), reason="fastapi+httpx required")
def test_wizard_definition_history_and_rollback(tmp_path: Path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    engine = _make_engine(tmp_path)
    app = FastAPI()
    app.include_router(build_router(engine=engine))
    client = TestClient(app)

    from importlib import import_module

    canonicalize_wizard_definition = import_module(
        "plugins.import.wizard_definition_model"
    ).canonicalize_wizard_definition

    base = client.get("/import/ui/wizard-definition").json()["definition"]
    graph = base.get("graph")
    assert isinstance(graph, dict)
    edges_any = graph.get("edges")
    assert isinstance(edges_any, list)
    assert len(edges_any) >= 3

    def _with_priority(edge_index: int, prio: int) -> dict:
        d = dict(base)
        g = dict(graph)
        edges: list[dict] = []
        for e in edges_any:
            edges.append(dict(e) if isinstance(e, dict) else {})
        if isinstance(edges[edge_index], dict):
            edges[edge_index]["priority"] = prio
        g["edges"] = edges
        d["graph"] = g
        return canonicalize_wizard_definition(d)

    d1 = _with_priority(0, 1)
    d2 = _with_priority(1, 2)

    assert client.post("/import/ui/wizard-definition", json={"definition": d1}).status_code == 200
    assert client.post("/import/ui/wizard-definition/activate", json={}).status_code == 200
    assert client.post("/import/ui/wizard-definition", json={"definition": d2}).status_code == 200
    assert client.post("/import/ui/wizard-definition/activate", json={}).status_code == 200

    hist = client.get("/import/ui/wizard-definition/history").json()["items"]
    ids = [it["id"] for it in hist]
    assert fingerprint_json(d1) in set(ids)

    rb = client.post(
        "/import/ui/wizard-definition/rollback",
        json={"id": fingerprint_json(d1)},
    )
    assert rb.status_code == 200
    cur = rb.json()["definition"]
    assert fingerprint_json(cur) == fingerprint_json(d1)

    nf = client.post(
        "/import/ui/wizard-definition/rollback",
        json={"id": "nope"},
    )
    assert nf.status_code == 404
