from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_patchhub_refresh_export_contract() -> None:
    path = _repo_root() / "scripts" / "patchhub" / "static" / "ph_refresh.js"
    content = path.read_text(encoding="utf-8")

    required = [
        "function refreshHeader(",
        "function refreshStats(",
        "window.PatchHubRefresh",
        "refreshHeader: refreshHeader",
        "refreshStats: refreshStats",
    ]

    for needle in required:
        assert needle in content, f"missing substring in ph_refresh.js: {needle}"


def test_patchhub_refresh_script_load_order() -> None:
    path = _repo_root() / "scripts" / "patchhub" / "templates" / "index.html"
    content = path.read_text(encoding="utf-8")

    a = "/static/ph_refresh.js"
    b = "/static/app.js"

    ia = content.find(a)
    ib = content.find(b)

    assert ia != -1, "missing /static/ph_refresh.js in index.html"
    assert ib != -1, "missing /static/app.js in index.html"
    assert ia < ib, "ph_refresh.js must load before app.js"


def test_patchhub_refresh_binding_contract() -> None:
    path = _repo_root() / "scripts" / "patchhub" / "static" / "app.js"
    content = path.read_text(encoding="utf-8")

    required = [
        "PatchHubRefresh.refreshHeader",
        "PatchHubRefresh.refreshStats",
    ]

    for needle in required:
        assert needle in content, f"missing binding in app.js: {needle}"
