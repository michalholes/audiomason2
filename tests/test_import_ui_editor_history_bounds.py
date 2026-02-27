"""Issue 243: Editor history boundedness (N=5) + ordering + rollback 404.

Scope: plugins/import only.
"""

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
def test_flow_config_history_is_bounded_and_ordered(tmp_path: Path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    engine = _make_engine(tmp_path)
    app = FastAPI()
    app.include_router(build_router(engine=engine))
    client = TestClient(app)

    base = client.post("/import/ui/config/reset", json={}).json()["config"]

    cfgs: list[dict] = []
    for i in range(6):
        cfg = dict(base)
        cfg["defaults"] = {"marker": i}
        cfgs.append(cfg)
        r = client.post("/import/ui/config", json={"config": cfg})
        assert r.status_code == 200
        a = client.post("/import/ui/config/activate", json={})
        assert a.status_code == 200

    hist = client.get("/import/ui/config/history").json()["items"]
    ids = [it["id"] for it in hist]

    expected = [
        fingerprint_json(cfgs[4]),
        fingerprint_json(cfgs[3]),
        fingerprint_json(cfgs[2]),
        fingerprint_json(cfgs[1]),
        fingerprint_json(cfgs[0]),
    ]
    assert ids == expected

    rb = client.post("/import/ui/config/rollback", json={"id": expected[2]})
    assert rb.status_code == 200
    out = rb.json()["config"]
    assert (out.get("defaults") or {}).get("marker") == 2

    nf = client.post("/import/ui/config/rollback", json={"id": "nope"})
    assert nf.status_code == 404


@pytest.mark.skipif((not _HAS_FASTAPI) or (not _HAS_HTTPX), reason="fastapi+httpx required")
def test_wizard_definition_history_is_bounded_and_ordered(tmp_path: Path) -> None:
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
    assert len(edges_any) >= 7

    # Generate valid variants by changing edge priority.
    defs: list[dict] = []
    for i in range(6):
        d = dict(base)
        g = dict(graph)
        edges: list[dict] = []
        for e in edges_any:
            edges.append(dict(e) if isinstance(e, dict) else {})
        if isinstance(edges[i], dict):
            edges[i]["priority"] = i + 1
        g["edges"] = edges
        d["graph"] = g
        defs.append(canonicalize_wizard_definition(d))
        r = client.post("/import/ui/wizard-definition", json={"definition": d})
        assert r.status_code == 200
        a = client.post("/import/ui/wizard-definition/activate", json={})
        assert a.status_code == 200
    hist = client.get("/import/ui/wizard-definition/history").json()["items"]
    ids = [it["id"] for it in hist]

    expected = [
        fingerprint_json(defs[4]),
        fingerprint_json(defs[3]),
        fingerprint_json(defs[2]),
        fingerprint_json(defs[1]),
        fingerprint_json(defs[0]),
    ]
    assert ids == expected

    rb = client.post("/import/ui/wizard-definition/rollback", json={"id": expected[1]})
    assert rb.status_code == 200
    out = rb.json()["definition"]
    out_graph = out.get("graph")
    assert isinstance(out_graph, dict)
    out_edges = out_graph.get("edges")
    assert isinstance(out_edges, list)
    # Rolled back to expected[1] == defs[3].
    out_canon = canonicalize_wizard_definition(out)
    assert fingerprint_json(out_canon) == fingerprint_json(defs[3])

    nf = client.post("/import/ui/wizard-definition/rollback", json={"id": "nope"})
    assert nf.status_code == 404
