"""Issue 106: v3 editor assets are served and loaded explicitly."""

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


ASSET_PATHS = [
    "/import/ui/assets/flow_json_clipboard.js",
    "/import/ui/assets/flow_json_modal_dom.js",
    "/import/ui/assets/dsl_editor/registry_api.js",
    "/import/ui/assets/dsl_editor/palette.js",
    "/import/ui/assets/dsl_editor/node_form.js",
    "/import/ui/assets/dsl_editor/edge_form.js",
    "/import/ui/assets/dsl_editor/raw_json.js",
    "/import/ui/assets/dsl_editor/graph_ops.js",
    "/import/ui/assets/dsl_editor/boot_v3.js",
    "/import/ui/assets/flow_json_modal_state.js",
    "/import/ui/assets/flow_json_modal_entrypoints.js",
]


def _make_engine(tmp_path: Path) -> ImportWizardEngine:
    roots = {
        name: tmp_path / name for name in ("inbox", "stage", "outbox", "jobs", "config", "wizards")
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
def test_import_ui_index_loads_v3_editor_assets_in_order(tmp_path: Path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    engine = _make_engine(tmp_path)
    app = FastAPI()
    app.include_router(build_router(engine=engine))
    client = TestClient(app)

    response = client.get("/import/ui/")
    assert response.status_code == 200
    html = response.text

    positions = []
    for asset_path in ASSET_PATHS:
        needle = f'<script src="{asset_path}"></script>'
        assert needle in html
        positions.append(html.index(needle))

    assert positions == sorted(positions)
    assert html.index("/import/ui/assets/dsl_editor/graph_ops.js") < html.index(
        "/import/ui/assets/dsl_editor/boot_v3.js"
    )
    assert html.index("/import/ui/assets/dsl_editor/boot_v3.js") < html.index(
        "/import/ui/assets/wizard_definition_editor.js"
    )
    assert html.index("/import/ui/assets/wizard_definition_editor.js") < html.index(
        "/import/ui/assets/flow_all_actions.js"
    )
    assert html.index("/import/ui/assets/flow_all_actions.js") < html.index(
        "/import/ui/assets/flow_json_modal_state.js"
    )
    assert html.index("/import/ui/assets/flow_json_modal_state.js") < html.index(
        "/import/ui/assets/flow_json_modal_entrypoints.js"
    )


@pytest.mark.skipif((not _HAS_FASTAPI) or (not _HAS_HTTPX), reason="fastapi+httpx required")
def test_import_ui_serves_v3_editor_assets(tmp_path: Path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    engine = _make_engine(tmp_path)
    app = FastAPI()
    app.include_router(build_router(engine=engine))
    client = TestClient(app)

    for asset_path in ASSET_PATHS:
        response = client.get(asset_path)
        assert response.status_code == 200, asset_path
        assert response.text


@pytest.mark.skipif((not _HAS_FASTAPI) or (not _HAS_HTTPX), reason="fastapi+httpx required")
def test_import_ui_index_exposes_flow_json_modal_controls(tmp_path: Path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    engine = _make_engine(tmp_path)
    app = FastAPI()
    app.include_router(build_router(engine=engine))
    client = TestClient(app)

    response = client.get("/import/ui/")
    assert response.status_code == 200
    html = response.text

    assert 'id="flowOpenWizardJson"' in html
    assert 'id="flowOpenConfigJson"' in html
    assert 'id="flowJsonModal"' in html
    assert 'id="flowJsonCopySelected"' in html
    assert 'id="flowJsonCopyAll"' in html
    assert 'id="flowJsonApply"' in html
    assert '<link rel="stylesheet" href="/import/ui/assets/flow_json_modal.css" />' in html
    assert html.index("/import/ui/assets/flow_json_modal_state.js") < html.index(
        "/import/ui/assets/flow_json_modal_entrypoints.js"
    )


@pytest.mark.skipif((not _HAS_FASTAPI) or (not _HAS_HTTPX), reason="fastapi+httpx required")
def test_import_ui_serves_flow_json_modal_layout_contract(tmp_path: Path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    engine = _make_engine(tmp_path)
    app = FastAPI()
    app.include_router(build_router(engine=engine))
    client = TestClient(app)

    css_response = client.get("/import/ui/assets/flow_json_modal.css")
    assert css_response.status_code == 200
    css = css_response.text
    assert "display: flex;" in css
    assert "flex-direction: column;" in css
    assert "overflow: hidden;" in css
    assert "flex: 1 1 320px;" in css
    assert "min-height: 180px;" in css
    assert "min-height: 520px;" not in css

    html_response = client.get("/import/ui/")
    assert html_response.status_code == 200
    html = html_response.text
    assert 'class="buttonRow flowJsonModalActionsBottom"' in html
    assert 'rows="16"' in html
