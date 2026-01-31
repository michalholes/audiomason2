"""Web Interface plugin (variant B).

Provides server-driven UI registry (navigation + page schemas) that can be consumed by a
modern SPA frontend renderer.

This plugin does NOT render HTML. It only exposes structured JSON schemas that describe
pages/layout, and uses existing AudioMason API endpoints as data sources.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from audiomason.core import ConfigResolver
from audiomason.core.loader import PluginLoader


@dataclass(frozen=True)
class UiNavItem:
    title: str
    route: str
    page_id: str


class WebInterfacePlugin:
    """Server-driven UI registry provider."""

    def __init__(self) -> None:
        self._config_resolver: ConfigResolver | None = None
        self._plugin_loader: PluginLoader | None = None
        self._verbosity: int = 1

        # Page registry (id -> schema dict)
        self._pages: dict[str, dict[str, Any]] = {}
        self._nav: list[UiNavItem] = []

    def attach(
        self,
        *,
        config_resolver: ConfigResolver | None,
        plugin_loader: PluginLoader | None,
        verbosity: int = 1,
    ) -> None:
        """Attach runtime context.

        Web server calls this after all plugins are loaded and ConfigResolver exists.
        """
        self._config_resolver = config_resolver
        self._plugin_loader = plugin_loader
        self._verbosity = verbosity
        self._rebuild_registry()

    def list_pages(self) -> list[dict[str, Any]]:
        """List page metadata."""
        return [
            {
                "id": page_id,
                "title": schema.get("title", page_id),
                "route": schema.get("route", f"/{page_id}"),
            }
            for page_id, schema in sorted(self._pages.items(), key=lambda kv: kv[0])
        ]

    def get_nav(self) -> list[dict[str, Any]]:
        return [{"title": i.title, "route": i.route, "page_id": i.page_id} for i in self._nav]

    def get_page(self, page_id: str) -> dict[str, Any] | None:
        return self._pages.get(page_id)


    def _validate_page_schema(self, page_id: str, schema: dict[str, Any]) -> dict[str, Any] | None:
        """Best-effort validation/coercion for page schemas.

        Returns a sanitized schema dict, or None if invalid.
        """
        if not isinstance(schema, dict):
            return None
        # Ensure id matches registry key.
        schema = dict(schema)
        schema.setdefault("id", page_id)
        schema["id"] = page_id
        # Optional common fields
        if "title" in schema and not isinstance(schema["title"], str):
            schema["title"] = str(schema["title"])
        schema.setdefault("title", page_id)
        if "route" in schema and not isinstance(schema["route"], str):
            schema["route"] = f"/{page_id}"
        schema.setdefault("route", f"/{page_id}")
        layout = schema.get("layout")
        if layout is None:
            return None
        if not isinstance(layout, dict):
            return None
        # Require a layout type.
        if not isinstance(layout.get("type"), str):
            return None
        return schema

    def _merge_plugin_contributions(
        self,
        *,
        pages: dict[str, dict[str, Any]],
        nav: list[UiNavItem],
    ) -> tuple[dict[str, dict[str, Any]], list[UiNavItem]]:
        """Merge pages/nav from other loaded plugins (best-effort).

        Conventions:
          - plugin.get_ui_pages() -> list[dict]
          - plugin.get_ui_nav_items() -> list[dict]
        """
        if not self._plugin_loader:
            return pages, nav
        for name in self._plugin_loader.list_plugins():
            if name == "web_interface":
                continue
            try:
                plug = self._plugin_loader.get_plugin(name)
            except Exception:
                continue
            # Pages
            if hasattr(plug, "get_ui_pages"):
                try:
                    contributed = plug.get_ui_pages()
                except Exception:
                    contributed = None
                if isinstance(contributed, list):
                    for item in contributed:
                        if not isinstance(item, dict):
                            continue
                        pid = item.get("id")
                        if not isinstance(pid, str) or not pid:
                            continue
                        validated = self._validate_page_schema(pid, item)
                        if validated is not None:
                            pages[pid] = validated
            # Nav
            if hasattr(plug, "get_ui_nav_items"):
                try:
                    contributed_nav = plug.get_ui_nav_items()
                except Exception:
                    contributed_nav = None
                if isinstance(contributed_nav, list):
                    for item in contributed_nav:
                        if not isinstance(item, dict):
                            continue
                        title = item.get("title")
                        route = item.get("route")
                        page = item.get("page_id")
                        if isinstance(title, str) and isinstance(route, str) and isinstance(page, str):
                            nav.append(UiNavItem(title=title, route=route, page_id=page))
        return pages, nav

    # -------------------------
    # Registry build
    # -------------------------

    def _rebuild_registry(self) -> None:
        pages: dict[str, dict[str, Any]] = {}
        nav: list[UiNavItem] = []

        # Built-in default pages (can be overridden later).
        for pid, schema in self._default_pages().items():
            validated = self._validate_page_schema(pid, schema)
            if validated is not None:
                pages[pid] = validated
        nav.extend(self._default_nav())

        # Merge contributions from other plugins (best-effort)
        pages, nav = self._merge_plugin_contributions(pages=pages, nav=nav)

        # Optional config overrides under web.ui.*
        # We treat these as pure overrides (no schema validation yet).
        cfg_pages = self._resolve_optional("web.ui.pages")
        if isinstance(cfg_pages, dict):
            for page_id, schema in cfg_pages.items():
                if isinstance(page_id, str) and isinstance(schema, dict):
                    validated = self._validate_page_schema(page_id, schema)
                    if validated is not None:
                        pages[page_id] = validated

        cfg_nav = self._resolve_optional("web.ui.nav")
        if isinstance(cfg_nav, list):
            nav = []
            for item in cfg_nav:
                if not isinstance(item, dict):
                    continue
                title = item.get("title")
                route = item.get("route")
                page = item.get("page_id")
                if isinstance(title, str) and isinstance(route, str) and isinstance(page, str):
                    nav.append(UiNavItem(title=title, route=route, page_id=page))

        # Future: allow other plugins to contribute pages/nav.
        self._pages = pages
        self._nav = nav

    def _resolve_optional(self, key: str) -> Any | None:
        if not self._config_resolver:
            return None
        try:
            value, _source = self._config_resolver.resolve(key)
            return value
        except Exception:
            return None

    def _default_nav(self) -> list[UiNavItem]:
        return [
            UiNavItem(title="Dashboard", route="/", page_id="dashboard"),
            UiNavItem(title="Jobs", route="/jobs", page_id="jobs"),
            UiNavItem(title="Config", route="/config", page_id="config"),
            UiNavItem(title="Logs", route="/logs", page_id="logs"),
        ]

    def _default_pages(self) -> dict[str, dict[str, Any]]:
        # This schema is intentionally minimal and stable.
        # A modern frontend renderer can interpret these component types.
        return {
            "dashboard": {
                "id": "dashboard",
                "title": "Dashboard",
                "route": "/",
                "layout": {
                    "type": "grid",
                    "cols": 12,
                    "gap": 4,
                    "children": [
                        {
                            "type": "card",
                            "colSpan": 4,
                            "title": "Status",
                            "content": {
                                "type": "stat_list",
                                "source": {"type": "api", "path": "/api/status"},
                                "fields": [
                                    {"label": "Version", "key": "version"},
                                    {"label": "Mode", "key": "mode"},
                                ],
                            },
                        },
                        {
                            "type": "card",
                            "colSpan": 8,
                            "title": "Jobs",
                            "content": {
                                "type": "table",
                                "source": {"type": "api", "path": "/api/jobs"},
                                "columns": [
                                    {"header": "ID", "key": "id"},
                                    {"header": "State", "key": "state"},
                                    {"header": "Title", "key": "title"},
                                ],
                                "rowClick": {"route": "/jobs/{id}"},
                            },
                        },
                        {
                            "type": "card",
                            "colSpan": 12,
                            "title": "Live logs",
                            "content": {"type": "log_stream", "source": {"type": "ws", "path": "/ws"}},
                        },
                    ],
                },
            },
            "jobs": {
                "id": "jobs",
                "title": "Jobs",
                "route": "/jobs",
                "layout": {
                    "type": "stack",
                    "gap": 4,
                    "children": [
                        {
                            "type": "card",
                            "title": "Jobs",
                            "content": {
                                "type": "table",
                                "source": {"type": "api", "path": "/api/jobs"},
                                "columns": [
                                    {"header": "ID", "key": "id"},
                                    {"header": "State", "key": "state"},
                                    {"header": "Title", "key": "title"},
                                ],
                            },
                        }
                    ],
                },
            },
            "config": {
                "id": "config",
                "title": "Config",
                "route": "/config",
                "layout": {
                    "type": "stack",
                    "gap": 4,
                    "children": [
                        {
                            "type": "card",
                            "title": "Effective config",
                            "content": {
                                "type": "json_view",
                                "source": {"type": "api", "path": "/api/config"},
                            },
                        }
                    ],
                },
            },
            "logs": {
                "id": "logs",
                "title": "Logs",
                "route": "/logs",
                "layout": {
                    "type": "stack",
                    "gap": 4,
                    "children": [
                        {
                            "type": "card",
                            "title": "Logs",
                            "content": {"type": "log_stream", "source": {"type": "ws", "path": "/ws"}},
                        }
                    ],
                },
            },
        }
