from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI

from .api.am_config import mount_am_config
from .api.fs import mount_fs
from .api.jobs import mount_jobs
from .api.logs import mount_logs
from .api.plugins_mgmt import mount_plugins_mgmt
from .api.roots import mount_roots
from .api.stage import mount_stage
from .api.ui_schema import mount_ui_schema
from .api.wizards import mount_wizards
from .ui_static import mount_ui_static
from .util.status import build_status


def _uvicorn_log_settings(verbosity: int) -> tuple[str, bool]:
    """Map AM verbosity to uvicorn log settings.

    Returns:
        (log_level, access_log)
    """
    if verbosity <= 0:
        return ("error", False)
    if verbosity == 1:
        return ("info", False)
    if verbosity == 2:
        return ("info", True)
    return ("debug", True)


def _silence_uvicorn_loggers() -> None:
    """Best-effort silencing for uvicorn loggers (quiet mode)."""
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = False
        logger.setLevel(logging.ERROR)


class WebInterfacePlugin:
    """Standalone web interface plugin (no dependency on other AM plugins)."""

    def create_app(
        self,
        *,
        config_resolver: Any | None = None,
        plugin_loader: Any | None = None,
        verbosity: int = 1,
    ) -> FastAPI:
        app = FastAPI(title="AudioMason Web Interface")

        app.state.config_resolver = config_resolver
        app.state.plugin_loader = plugin_loader
        app.state.verbosity = int(verbosity)

        # API first (avoid catch-all swallowing /api/*)
        mount_am_config(app)
        mount_ui_schema(app)
        mount_plugins_mgmt(app)
        mount_roots(app)
        mount_fs(app)
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

    def run(
        self,
        host: str,
        port: int,
        *,
        config_resolver: Any | None = None,
        plugin_loader: Any | None = None,
        verbosity: int = 1,
    ) -> None:
        """Run the web server in a standalone (non-async) context."""
        try:
            import uvicorn
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "Missing dependency: uvicorn. Install in venv: pip install uvicorn"
            ) from e
        app = self.create_app(
            config_resolver=config_resolver, plugin_loader=plugin_loader, verbosity=verbosity
        )
        log_level, access_log = _uvicorn_log_settings(int(verbosity))
        if int(verbosity) <= 0:
            _silence_uvicorn_loggers()
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level=log_level,
            access_log=access_log,
        )

    async def serve(
        self,
        host: str,
        port: int,
        *,
        config_resolver: Any | None = None,
        plugin_loader: Any | None = None,
        verbosity: int = 1,
    ) -> None:
        """Serve the web server inside an existing asyncio event loop."""
        try:
            import uvicorn
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "Missing dependency: uvicorn. Install in venv: pip install uvicorn"
            ) from e
        app = self.create_app(
            config_resolver=config_resolver, plugin_loader=plugin_loader, verbosity=verbosity
        )
        log_level, access_log = _uvicorn_log_settings(int(verbosity))
        if int(verbosity) <= 0:
            _silence_uvicorn_loggers()
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level=log_level,
            access_log=access_log,
        )
        server = uvicorn.Server(config)
        await server.serve()
