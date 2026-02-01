from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from ..util.paths import ui_overrides_path
import json


def _default_nav() -> list[dict[str, Any]]:
    return [
        {"title": "Dashboard", "route": "/", "page_id": "dashboard"},
        {"title": "Config", "route": "/config", "page_id": "config"},
        {"title": "Plugins", "route": "/plugins", "page_id": "plugins"},
        {"title": "Stage", "route": "/stage", "page_id": "stage"},
        {"title": "Wizards", "route": "/wizards", "page_id": "wizards"},
        {"title": "Logs", "route": "/logs", "page_id": "logs"},
        {"title": "UI Config", "route": "/ui-config", "page_id": "ui_config"},
    ]


def _default_pages() -> dict[str, dict[str, Any]]:
    return {
        "dashboard": {
            "id": "dashboard",
            "title": "Dashboard",
            "layout": {
                "type": "grid",
                "children": [
                    {
                        "type": "card",
                        "title": "Status",
                        "content": {
                            "type": "stat_list",
                            "source": {"type": "api", "path": "/api/status"},
                            "fields": [
                                {"label": "pid", "key": "pid"},
                                {"label": "uptime_s", "key": "uptime_s"},
                            ],
                        },
                    }
                ],
            },
        },
        "config": {
            "id": "config",
            "title": "Config",
            "layout": {
                "type": "grid",
                "children": [
                    {
                        "type": "card",
                        "title": "AudioMason config.yaml",
                        "content": {
                            "type": "yaml_editor",
                            "source": {"type": "api", "path": "/api/am/config"},
                            "save": {"type": "api", "method": "PUT", "path": "/api/am/config"},
                            "field": "yaml",
                        },
                    }
                ],
            },
        },
        "plugins": {
            "id": "plugins",
            "title": "Plugins",
            "layout": {
                "type": "grid",
                "children": [
                    {"type": "plugin_manager"}
                ],
            },
        },
        "stage": {
            "id": "stage",
            "title": "Stage",
            "layout": {"type": "grid", "children": [{"type": "stage_manager"}]},
        },
        "wizards": {
            "id": "wizards",
            "title": "Wizards",
            "layout": {"type": "grid", "children": [{"type": "wizard_manager"}]},
        },
        "logs": {
            "id": "logs",
            "title": "Logs",
            "layout": {
                "type": "grid",
                "children": [
                    {
                        "type": "card",
                        "title": "Server logs",
                        "content": {"type": "log_stream"},
                    }
                ],
            },
        },
        "ui_config": {
            "id": "ui_config",
            "title": "UI Config",
            "layout": {
                "type": "grid",
                "children": [
                    {
                        "type": "card",
                        "title": "UI overrides",
                        "content": {
                            "type": "json_editor",
                            "source": {"type": "api", "path": "/api/ui/config"},
                            "save": {"type": "api", "method": "PUT", "path": "/api/ui/config"},
                            "field": "data",
                        },
                    }
                ],
            },
        },
    }


def _load_overrides() -> dict[str, Any]:
    p = ui_overrides_path()
    if not p.exists():
        return {"pages": {}, "nav": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"pages": {}, "nav": []}


def mount_ui_schema(app: FastAPI) -> None:
    @app.get("/api/ui/nav")
    def ui_nav() -> dict[str, Any]:
        ov = _load_overrides()
        nav = ov.get("nav")
        if isinstance(nav, list) and nav:
            return {"items": nav}
        return {"items": _default_nav()}

    @app.get("/api/ui/pages")
    def ui_pages() -> dict[str, Any]:
        pages = _default_pages()
        ov = _load_overrides()
        pov = ov.get("pages")
        if isinstance(pov, dict):
            for k, v in pov.items():
                if isinstance(v, dict):
                    pages[k] = v
        return {"items": [{"id": k, "title": v.get("title", k)} for k, v in pages.items()]}

    @app.get("/api/ui/page/{page_id}")
    def ui_page(page_id: str) -> dict[str, Any]:
        pages = _default_pages()
        ov = _load_overrides()
        pov = ov.get("pages")
        if isinstance(pov, dict) and page_id in pov and isinstance(pov[page_id], dict):
            pages[page_id] = pov[page_id]
        return pages.get(page_id, pages["dashboard"])

    @app.get("/api/ui/config")
    def ui_config_get() -> dict[str, Any]:
        p = ui_overrides_path()
        return {"path": str(p), "data": _load_overrides()}

    @app.put("/api/ui/config")
    def ui_config_put(body: dict[str, Any]) -> dict[str, Any]:
        p = ui_overrides_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        data = body.get("data")
        if not isinstance(data, dict):
            data = {"pages": {}, "nav": []}
        p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"ok": True, "path": str(p)}
