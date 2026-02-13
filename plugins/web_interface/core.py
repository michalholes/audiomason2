from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any

from fastapi import FastAPI, Request

from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus

from .api.am_config import mount_am_config
from .api.fs import mount_fs
from .api.import_wizard import mount_import_wizard
from .api.jobs import mount_jobs
from .api.logs import mount_logs
from .api.plugins_mgmt import mount_plugins_mgmt
from .api.roots import mount_roots
from .api.stage import mount_stage
from .api.ui_schema import mount_ui_schema
from .api.wizards import mount_wizards
from .ui_static import mount_ui_static
from .util.diag_stream import install_event_tap
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
        # Tap the core EventBus once per process so the Logs UI can stream
        # diagnostics/events without tailing a web-specific log file.
        install_event_tap()

        @app.middleware("http")
        async def _emit_route_boundary(request: Request, call_next: Any) -> Any:
            # Emit deterministic call-boundary diagnostics for each API route.
            path = request.url.path
            method = request.method
            op = f"{method} {path}"
            start_env = build_envelope(
                event="boundary.start",
                component="web_interface",
                operation=op,
                data={"path": path, "method": method},
            )
            with suppress(Exception):
                get_event_bus().publish("boundary.start", start_env)

            t0 = __import__("time").monotonic()
            try:
                response = await call_next(request)
            except Exception as e:
                dur_ms = int((__import__("time").monotonic() - t0) * 1000)
                fail_env = build_envelope(
                    event="boundary.end",
                    component="web_interface",
                    operation=op,
                    data={
                        "status": "failed",
                        "error_type": type(e).__name__,
                        "error": str(e),
                        "duration_ms": dur_ms,
                    },
                )
                with suppress(Exception):
                    get_event_bus().publish("boundary.end", fail_env)
                raise

            dur_ms = int((__import__("time").monotonic() - t0) * 1000)
            end_env = build_envelope(
                event="boundary.end",
                component="web_interface",
                operation=op,
                data={
                    "status": "succeeded",
                    "status_code": int(getattr(response, "status_code", 200)),
                    "duration_ms": dur_ms,
                },
            )
            # In debug verbosity, include a small amount of extra data.
            if int(getattr(request.app.state, "verbosity", 1)) >= 3:
                with suppress(Exception):
                    end_env["data"]["query"] = dict(request.query_params)
            with suppress(Exception):
                get_event_bus().publish("boundary.end", end_env)

            return response

        # API first (avoid catch-all swallowing /api/*)
        mount_am_config(app)
        mount_ui_schema(app)
        mount_plugins_mgmt(app)
        mount_roots(app)
        mount_fs(app)
        mount_stage(app)
        mount_wizards(app)
        mount_import_wizard(app)
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
            config_resolver=config_resolver,
            plugin_loader=plugin_loader,
            verbosity=verbosity,
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
            config_resolver=config_resolver,
            plugin_loader=plugin_loader,
            verbosity=verbosity,
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
