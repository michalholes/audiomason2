from __future__ import annotations

import inspect
import logging
import sys
import traceback
from contextlib import suppress
from typing import Protocol, runtime_checkable

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from audiomason.core.diagnostics import build_envelope
from audiomason.core.errors import PluginNotFoundError
from audiomason.core.events import get_event_bus
from audiomason.core.logging import get_logger

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
from .util.diag_stream import install_event_tap
from .util.status import build_status


@runtime_checkable
class _SupportsGetPlugin(Protocol):
    def get_plugin(self, plugin_name: str) -> object: ...


@runtime_checkable
class _SupportsFastApiRouter(Protocol):
    def get_fastapi_router(self) -> APIRouter | None: ...


def _uvicorn_log_settings(verbosity: int) -> tuple[str, bool]:
    """Map AM verbosity to uvicorn log settings.

    Returns:
        (log_level, access_log)
    """
    # Access logs are intentionally kept off even in debug mode.
    # Debug visibility is provided via deterministic diagnostics emission
    # (boundary.start / boundary.end) instead of GET spam.
    if verbosity <= 0:
        return ("error", False)
    if verbosity <= 2:
        return ("info", False)
    return ("debug", False)


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
        config_resolver: object | None = None,
        plugin_loader: object | None = None,
        verbosity: int = 1,
    ) -> FastAPI:
        app = FastAPI(title="AudioMason Web Interface")
        web_logger = get_logger("web_interface")
        web_verbosity = int(verbosity)

        app.state.config_resolver = config_resolver
        app.state.plugin_loader = plugin_loader
        app.state.verbosity = web_verbosity
        app.state.web_logger = web_logger
        # Tap the core EventBus once per process so the Logs UI can stream
        # diagnostics/events without tailing a web-specific log file.
        install_event_tap()

        async def _emit_route_boundary(
            request: Request,
            call_next: RequestResponseEndpoint,
        ) -> Response:
            # Emit deterministic call-boundary diagnostics for each HTTP route.
            path = request.url.path
            method = request.method
            op = f"{method} {path}"

            def _ascii(text: str) -> str:
                return (text or "").encode("ascii", "backslashreplace").decode("ascii")

            start_data: dict[str, object] = {"path": path, "method": method}
            if web_verbosity >= 3:
                with suppress(Exception):
                    start_data["query"] = dict(request.query_params)

            start_env = build_envelope(
                event="boundary.start",
                component="web_interface",
                operation=op,
                data=start_data,
            )
            with suppress(Exception):
                get_event_bus().publish("boundary.start", start_env)
            with suppress(Exception):
                web_logger.info(_ascii(f"{op}: start {start_data}"))

            import time as _time

            t0 = _time.monotonic()
            try:
                response = await call_next(request)
            except Exception as e:
                dur_ms = int((_time.monotonic() - t0) * 1000)
                try:
                    tb = traceback.format_exc()
                except Exception:
                    tb = None

                fail_data: dict[str, object] = {
                    "status": "failed",
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "traceback": tb,
                    "duration_ms": dur_ms,
                }
                fail_env = build_envelope(
                    event="boundary.end",
                    component="web_interface",
                    operation=op,
                    data=fail_data,
                )
                with suppress(Exception):
                    get_event_bus().publish("boundary.end", fail_env)
                with suppress(Exception):
                    web_logger.error(_ascii(f"{op}: failed {fail_data}"))
                raise

            dur_ms = int((_time.monotonic() - t0) * 1000)
            end_data: dict[str, object] = {
                "status": "succeeded",
                "status_code": response.status_code,
                "duration_ms": dur_ms,
            }
            end_env = build_envelope(
                event="boundary.end",
                component="web_interface",
                operation=op,
                data=end_data,
            )
            with suppress(Exception):
                get_event_bus().publish("boundary.end", end_env)
            with suppress(Exception):
                web_logger.info(_ascii(f"{op}: end {end_data}"))

            return response

        app.add_middleware(BaseHTTPMiddleware, dispatch=_emit_route_boundary)

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

        # Mount UI routes provided by the import plugin (thin renderer contract).
        # Fail-safe: absence or failure must not crash web_interface.
        def _try_mount_import_ui() -> None:
            loader = plugin_loader
            logger = web_logger
            verbosity = web_verbosity

            def _emit(event: str, data: dict[str, object]) -> None:
                env = build_envelope(
                    event=event,
                    component="web_interface",
                    operation="import_ui_mount",
                    data=data,
                )
                with suppress(Exception):
                    get_event_bus().publish(event, env)

            def _plugin_origin(p: object | None) -> str | None:
                if p is None:
                    return None
                module_name = p.__class__.__module__
                if module_name:
                    mod = sys.modules.get(module_name)
                    module_file = inspect.getsourcefile(mod) if mod is not None else None
                    if isinstance(module_file, str) and module_file:
                        return module_file
                try:
                    return repr(p)
                except Exception:
                    return None

            plugin: object | None = None

            if not isinstance(loader, _SupportsGetPlugin):
                _emit(
                    "web_interface.import_ui_mount_failed",
                    {
                        "phase": "get_plugin",
                        "exc_type": "TypeError",
                        "exc_message": "plugin_loader has no get_plugin",
                        "plugin_origin": None,
                    },
                )
                logger.info("import_ui_mount: failed phase=get_plugin origin=None")
                return

            try:
                plugin = loader.get_plugin("import")
            except PluginNotFoundError as exc:
                _emit(
                    "web_interface.import_ui_mount_failed",
                    {
                        "phase": "get_plugin",
                        "exc_type": type(exc).__name__,
                        "exc_message": str(exc),
                        "plugin_origin": None,
                    },
                )
                logger.info("import_ui_mount: failed phase=get_plugin origin=None")
                if verbosity >= 3:
                    logger.debug(f"import_ui_mount: get_plugin failed: {exc!r}")
                return
            except Exception as exc:
                _emit(
                    "web_interface.import_ui_mount_failed",
                    {
                        "phase": "get_plugin",
                        "exc_type": type(exc).__name__,
                        "exc_message": str(exc),
                        "plugin_origin": None,
                    },
                )
                logger.info("import_ui_mount: failed phase=get_plugin origin=None")
                if verbosity >= 3:
                    logger.debug(f"import_ui_mount: get_plugin failed: {exc!r}")
                return

            plugin_origin = _plugin_origin(plugin)
            if not isinstance(plugin, _SupportsFastApiRouter):
                _emit(
                    "web_interface.import_ui_mount_failed",
                    {
                        "phase": "build_router",
                        "exc_type": "AttributeError",
                        "exc_message": "plugin has no get_fastapi_router",
                        "plugin_origin": plugin_origin,
                    },
                )
                logger.info(f"import_ui_mount: failed phase=build_router origin={plugin_origin}")
                return

            try:
                router = plugin.get_fastapi_router()
            except Exception as exc:
                _emit(
                    "web_interface.import_ui_mount_failed",
                    {
                        "phase": "build_router",
                        "exc_type": type(exc).__name__,
                        "exc_message": str(exc),
                        "plugin_origin": plugin_origin,
                    },
                )
                logger.info(f"import_ui_mount: failed phase=build_router origin={plugin_origin}")
                if verbosity >= 3:
                    logger.debug(f"import_ui_mount: build_router failed: {exc!r}")
                return

            if router is None:
                _emit(
                    "web_interface.import_ui_mount_failed",
                    {
                        "phase": "build_router",
                        "exc_type": "ValueError",
                        "exc_message": "get_fastapi_router returned None",
                        "plugin_origin": plugin_origin,
                    },
                )
                logger.info(f"import_ui_mount: failed phase=build_router origin={plugin_origin}")
                return

            try:
                app.include_router(router)
            except Exception as exc:
                _emit(
                    "web_interface.import_ui_mount_failed",
                    {
                        "phase": "include_router",
                        "exc_type": type(exc).__name__,
                        "exc_message": str(exc),
                        "plugin_origin": plugin_origin,
                    },
                )
                logger.info(f"import_ui_mount: failed phase=include_router origin={plugin_origin}")
                if verbosity >= 3:
                    logger.debug(f"import_ui_mount: include_router failed: {exc!r}")
                return

            _emit(
                "web_interface.import_ui_mount_ok",
                {"plugin_origin": plugin_origin},
            )
            logger.info(f"import_ui_mount: ok (origin={plugin_origin})")

        _try_mount_import_ui()

        # Import Wizard is explicitly not implemented in web_interface.
        # Provide a deterministic 404 for all HTTP methods under /api/import_wizard/*
        # to avoid SPA fallback producing 405 for POST/PUT/etc.
        def api_import_wizard_removed(rest: str) -> JSONResponse:  # noqa: ARG001
            content: dict[str, str] = {"detail": "Not Found"}
            return JSONResponse(status_code=404, content=content)

        def api_health() -> dict[str, object]:
            return {"ok": True}

        def api_status() -> dict[str, object]:
            return build_status()

        app.add_api_route(
            "/api/import_wizard/{rest:path}",
            api_import_wizard_removed,
            methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
        )
        app.add_api_route("/api/health", api_health, methods=["GET"])
        app.add_api_route("/api/status", api_status, methods=["GET"])

        # UI static + SPA fallback last
        mount_ui_static(app)

        return app

    def run(
        self,
        host: str,
        port: int,
        *,
        config_resolver: object | None = None,
        plugin_loader: object | None = None,
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
        config_resolver: object | None = None,
        plugin_loader: object | None = None,
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
