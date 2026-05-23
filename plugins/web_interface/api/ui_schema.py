from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from fastapi import FastAPI

from audiomason.core.serde import json_loads_object

from ..util.paths import debug_enabled, ui_overrides_path
from .debug_bundle import mount_debug_bundle


def _dict_str_object(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    mapping = cast(Mapping[object, object], value)
    out: dict[str, object] = {}
    for key, item in mapping.items():
        if isinstance(key, str):
            out[key] = item
    return out


def _default_nav() -> list[dict[str, object]]:
    nav: list[dict[str, object]] = [
        {"title": "Dashboard", "route": "/", "page_id": "dashboard"},
        {"title": "Config", "route": "/config", "page_id": "config"},
        {"title": "Plugins", "route": "/plugins", "page_id": "plugins"},
        {"title": "Stage", "route": "/stage", "page_id": "stage"},
        {"title": "Import", "route": "/import", "page_id": "import"},
        {"title": "Wizards", "route": "/wizards", "page_id": "wizards"},
        {"title": "Jobs", "route": "/jobs", "page_id": "jobs"},
        {"title": "Logs", "route": "/logs", "page_id": "logs"},
        {"title": "UI Config", "route": "/ui-config", "page_id": "ui_config"},
    ]

    if debug_enabled():
        nav.append({"title": "Debug JS", "route": "/debug-js", "page_id": "debug_js"})

    return nav


def _default_pages() -> dict[str, dict[str, object]]:
    pages: dict[str, dict[str, object]] = {
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
                    },
                    {
                        "type": "card",
                        "title": "Run wizard here",
                        "content": {"type": "root_browser"},
                    },
                ],
            },
        },
        "config": {
            "id": "config",
            "title": "Config",
            "layout": {
                "type": "grid",
                "children": [{"type": "am_config"}],
            },
        },
        "plugins": {
            "id": "plugins",
            "title": "Plugins",
            "layout": {
                "type": "grid",
                "children": [{"type": "plugin_manager"}],
            },
        },
        "stage": {
            "id": "stage",
            "title": "Stage",
            "layout": {"type": "grid", "children": [{"type": "stage_manager"}]},
        },
        "import": {
            "id": "import",
            "title": "Import",
            "layout": {
                "type": "grid",
                "children": [
                    {
                        "type": "card",
                        "title": "Import wizard",
                        "content": {"type": "import_wizard"},
                    }
                ],
            },
        },
        "wizards": {
            "id": "wizards",
            "title": "Wizards",
            "layout": {"type": "grid", "children": [{"type": "wizard_manager"}]},
        },
        "jobs": {
            "id": "jobs",
            "title": "Jobs",
            "layout": {"type": "grid", "children": [{"type": "jobs_log_viewer"}]},
        },
        "logs": {
            "id": "logs",
            "title": "Logs",
            "layout": {
                "type": "grid",
                "children": [
                    {
                        "type": "card",
                        "title": "Debug bundle",
                        "content": {
                            "type": "button_row",
                            "buttons": [
                                {
                                    "label": "Download debug bundle",
                                    "action": {
                                        "type": "download",
                                        "href": "/api/debug/bundle",
                                    },
                                }
                            ],
                        },
                    },
                    {
                        "type": "card",
                        "title": "EventBus (diagnostics)",
                        "content": {
                            "type": "log_stream",
                            "stream_kind": "eventbus",
                            "tail_source": {
                                "type": "api",
                                "path": "/api/logs/tail?lines=200",
                            },
                            "source": {
                                "type": "sse",
                                "path": "/api/logs/stream?since_id=0",
                            },
                        },
                    },
                    {
                        "type": "card",
                        "title": "LogBus (core logs)",
                        "content": {
                            "type": "log_stream",
                            "stream_kind": "logbus",
                            "tail_source": {
                                "type": "api",
                                "path": "/api/logbus/tail?lines=200",
                            },
                            "source": {
                                "type": "sse",
                                "path": "/api/logbus/stream?since_id=0",
                            },
                        },
                    },
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
                            "save_action": {
                                "type": "api",
                                "method": "PUT",
                                "path": "/api/ui/config",
                            },
                            "field": "data",
                        },
                    }
                ],
            },
        },
    }

    if debug_enabled():
        # In debug mode, surface browser-side debug information in the same place
        # as all other logs (no DevTools required).
        logs_page = pages.get("logs")
        if logs_page is not None:
            layout = _dict_str_object(logs_page.get("layout"))
            logs_children = layout.get("children")
            if isinstance(logs_children, list):
                children = cast(list[object], logs_children)
                debug_feed_content: dict[str, str] = {"type": "ui_debug_feed"}
                debug_card: dict[str, object] = {
                    "type": "card",
                    "title": "Browser debug (client-side)",
                    "content": debug_feed_content,
                }
                children.insert(
                    0,
                    debug_card,
                )

    if debug_enabled():
        pages["debug_js"] = {
            "id": "debug_js",
            "title": "Debug JS",
            "layout": {
                "type": "grid",
                "children": [
                    {
                        "type": "card",
                        "title": "JavaScript errors",
                        "content": {"type": "js_error_feed"},
                    }
                ],
            },
        }

    return pages


def _load_overrides() -> dict[str, object]:
    p = ui_overrides_path()
    if not p.exists():
        return {"pages": {}, "nav": []}
    try:
        loaded = json_loads_object(p.read_text(encoding="utf-8"))
        return _dict_str_object(loaded)
    except Exception:
        return {"pages": {}, "nav": []}


def mount_ui_schema(app: FastAPI) -> None:
    mount_debug_bundle(app)

    def ui_schema() -> dict[str, object]:
        """Developer-friendly schema snapshot.

        This is not an OpenAPI replacement. It exposes the UI nav/pages schema and
        the primary configuration hooks used by the web interface.
        """

        return {
            "nav": _default_nav(),
            "pages": _default_pages(),
            "ui_overrides": {
                "path": str(ui_overrides_path()),
                "format": "json",
                "default": {"pages": {}, "nav": []},
            },
            "env": {
                "WEB_INTERFACE_DEBUG": (
                    "if truthy, API responses may include extra diagnostic fields"
                ),
                "WEB_INTERFACE_STAGE_DIR": "override the stage upload directory",
                "WEB_INTERFACE_LOG_PATH": "optional log file path for server log tail/stream",
            },
        }

    def ui_nav() -> dict[str, object]:
        ov = _load_overrides()
        nav = ov.get("nav")
        if isinstance(nav, list) and nav:
            return {"items": nav}
        return {"items": _default_nav()}

    def ui_pages() -> dict[str, object]:
        pages = _default_pages()
        ov = _load_overrides()
        pov = ov.get("pages")
        if isinstance(pov, Mapping):
            pov_map = cast(Mapping[object, object], pov)
            for k, v in pov_map.items():
                if isinstance(k, str) and isinstance(v, Mapping):
                    pages[k] = _dict_str_object(cast(object, v))
        return {"items": [{"id": k, "title": v.get("title", k)} for k, v in pages.items()]}

    def ui_page(page_id: str) -> dict[str, object]:
        pages = _default_pages()
        ov = _load_overrides()
        pov = _dict_str_object(ov.get("pages"))
        override_page = pov.get(page_id)
        if isinstance(override_page, Mapping):
            pages[page_id] = _dict_str_object(cast(object, override_page))
        return pages.get(page_id, pages["dashboard"])

    def ui_config_get() -> dict[str, object]:
        p = ui_overrides_path()
        out: dict[str, object] = {"data": _load_overrides(), "info": ""}
        if p.exists():
            out["info"] = "user"
        if debug_enabled():
            out["path"] = str(p)
        return out

    def ui_config_put(body: dict[str, object]) -> dict[str, object]:
        p = ui_overrides_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        data = body.get("data")
        data_out: dict[str, object] = _dict_str_object(data)
        if not data_out:
            data_out = dict(body) if body else {"pages": cast(object, {}), "nav": cast(object, [])}
        p.write_text(json.dumps(data_out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        out: dict[str, object] = {"ok": True, "info": "user"}
        if debug_enabled():
            out["path"] = str(p)
        return out

    app.add_api_route("/api/ui/schema", ui_schema, methods=["GET"])
    app.add_api_route("/api/ui/nav", ui_nav, methods=["GET"])
    app.add_api_route("/api/ui/pages", ui_pages, methods=["GET"])
    app.add_api_route("/api/ui/page/{page_id}", ui_page, methods=["GET"])
    app.add_api_route("/api/ui/config", ui_config_get, methods=["GET"])
    app.add_api_route("/api/ui/config", ui_config_put, methods=["PUT"])
