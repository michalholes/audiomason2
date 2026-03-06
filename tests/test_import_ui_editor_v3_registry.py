"""Issue 106: v3 editor registry path uses existing endpoints only."""

from __future__ import annotations

import re
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


ALLOWED_UI_ENDPOINTS = {
    "/import/ui/primitive-registry",
    "/import/ui/wizard-definition",
    "/import/ui/wizard-definition/validate",
    "/import/ui/wizard-definition/activate",
    "/import/ui/wizard-definition/reset",
    "/import/ui/wizard-definition/history",
    "/import/ui/wizard-definition/rollback",
}


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
def test_import_ui_v3_registry_endpoint_returns_bootstrapped_primitives(tmp_path: Path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    engine = _make_engine(tmp_path)
    app = FastAPI()
    app.include_router(build_router(engine=engine))
    client = TestClient(app)

    response = client.get("/import/ui/primitive-registry")
    assert response.status_code == 200
    registry = response.json()["registry"]
    assert registry["registry_version"] == 1
    primitive_ids = {str(item.get("primitive_id")) for item in registry.get("primitives", [])}
    assert primitive_ids
    assert all(primitive_ids)
    assert "select_authors" in primitive_ids


def test_v3_registry_api_module_uses_existing_editor_endpoints_only() -> None:
    source = Path("plugins/import/ui/web/assets/dsl_editor/registry_api.js").read_text(
        encoding="utf-8"
    )
    endpoints = set(re.findall(r'"(/import/ui/[^"]+)"', source))
    assert endpoints == ALLOWED_UI_ENDPOINTS
