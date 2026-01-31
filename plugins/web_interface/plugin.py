from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn


@dataclass(frozen=True)
class NavItem:
    title: str
    route: str
    page_id: str


class WebInterfacePlugin:
    """Modern server-driven web interface plugin.

    This plugin starts its own FastAPI/uvicorn server and does NOT depend on the legacy
    web_server plugin.
    """

    name = "web_interface"

    def __init__(self) -> None:
        self.config_resolver = None
        self.plugin_loader = None
        self.verbosity = 1

        self._pages: dict[str, dict[str, Any]] = {}
        self._nav: list[NavItem] = []

    def _default_pages(self) -> dict[str, dict[str, Any]]:
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
                                    {"label": "Version", "key": "version"},
                                    {"label": "Mode", "key": "mode"},
                                ],
                            },
                        },
                    ],
                },
            },
            "logs": {
                "id": "logs",
                "title": "Logs",
                "layout": {
                    "type": "grid",
                    "children": [
                        {
                            "type": "card",
                            "title": "Note",
                            "content": {
                                "type": "stat_list",
                                "source": {"type": "api", "path": "/api/logs/tail"},
                                "fields": [{"label": "info", "key": "info"}],
                            },
                        }
                    ],
                },
            },
        }

    def _default_nav(self) -> list[NavItem]:
        return [
            NavItem(title="Dashboard", route="/", page_id="dashboard"),
            NavItem(title="Logs", route="/logs", page_id="logs"),
        ]

    def _resolve(self, key: str, default: Any) -> Any:
        if self.config_resolver is None:
            return default
        try:
            value, _source = self.config_resolver.resolve(key)
            return value
        except Exception:
            return default

    def get_ui_static_dir(self) -> Path:
        return Path(__file__).parent / "ui"

    def build_registry(self) -> None:
        # For now: defaults only. (Config overrides can be added later.)
        self._pages = self._default_pages()
        self._nav = self._default_nav()

    def create_app(self) -> FastAPI:
        self.build_registry()
        app = FastAPI(title="AudioMason Web Interface")

        ui_dir = self.get_ui_static_dir()
        assets_dir = ui_dir / "assets"
        app.mount("/ui/assets", StaticFiles(directory=str(assets_dir)), name="ui-assets")

        @app.get("/ui/")
        def ui_index() -> FileResponse:
            return FileResponse(str(ui_dir / "index.html"))

        @app.get("/ui/{path:path}")
        def ui_fallback(path: str) -> FileResponse:
            # SPA fallback
            return FileResponse(str(ui_dir / "index.html"))

        @app.get("/api/ui/nav")
        def api_ui_nav() -> dict[str, Any]:
            return {"items": [item.__dict__ for item in self._nav]}

        @app.get("/api/ui/pages")
        def api_ui_pages() -> dict[str, Any]:
            items = [{"id": p.get("id", pid), "title": p.get("title", pid)} for pid, p in self._pages.items()]
            return {"items": items}

        @app.get("/api/ui/page/{page_id}")
        def api_ui_page(page_id: str) -> dict[str, Any]:
            if page_id not in self._pages:
                raise HTTPException(status_code=404, detail="page not found")
            return self._pages[page_id]

        # Minimal APIs for MVP so the renderer has something to show
        @app.get("/api/status")
        def api_status() -> dict[str, Any]:
            # Best-effort: if State exists and is wired later, this can be expanded
            return {"version": "unknown", "mode": "normal"}

        @app.get("/api/logs/tail")
        def api_logs_tail() -> dict[str, Any]:
            return {"info": "log streaming not implemented yet"}

        return app

    async def run(self) -> None:
        host = self._resolve("web_interface.host", "0.0.0.0")
        port = int(self._resolve("web_interface.port", 8081))

        app = self.create_app()

        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()
