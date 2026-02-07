from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from .api.am_config import mount_am_config
from .api.jobs import mount_jobs
from .api.logs import mount_logs
from .api.plugins_mgmt import mount_plugins_mgmt
from .api.stage import mount_stage
from .api.ui_schema import mount_ui_schema
from .api.wizards import mount_wizards
from .ui_static import mount_ui_static
from .util.status import build_status


class WebInterfacePlugin:
    """Standalone web interface plugin (no dependency on other AM plugins)."""

    def create_app(self) -> FastAPI:
        app = FastAPI(title="AudioMason Web Interface")

        # API first (avoid catch-all swallowing /api/*)
        mount_am_config(app)
        mount_ui_schema(app)
        mount_plugins_mgmt(app)
        mount_stage(app)
        mount_wizards(app)
        mount_logs(app)
        mount_jobs(app)

        @app.get("/api/health")
        def api_health() -> dict[str, Any]:
            return {"ok": True}

        @app.get("/api/status")
        def api_status() -> dict[str, Any]:
            return build_status()

        # UI static + SPA fallback last
        mount_ui_static(app)

        return app

    def run(self, host: str, port: int) -> None:
        """Run the web server in a standalone (non-async) context."""
        try:
            import uvicorn
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "Missing dependency: uvicorn. Install in venv: pip install uvicorn"
            ) from e
        app = self.create_app()
        uvicorn.run(app, host=host, port=port, log_level="info")

    async def serve(self, host: str, port: int) -> None:
        """Serve the web server inside an existing asyncio event loop."""
        try:
            import uvicorn
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "Missing dependency: uvicorn. Install in venv: pip install uvicorn"
            ) from e
        app = self.create_app()
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()
