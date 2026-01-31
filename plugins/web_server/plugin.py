"""Web Server plugin - FastAPI REST API + Jinja2 Web UI.

Provides complete web interface for AudioMason control with dynamic templates.
"""

from __future__ import annotations

import asyncio
import json
import uuid
import random
from pathlib import Path
from typing import Any

try:
    from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect, Request
    from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.templating import Jinja2Templates
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    FastAPI = None
    File = None
    Form = None
    UploadFile = None
    WebSocket = None
    WebSocketDisconnect = None
    HTMLResponse = None
    JSONResponse = None
    RedirectResponse = None
    StaticFiles = None
    Jinja2Templates = None
    uvicorn = None
    Request = None

from audiomason.core import (
    ConfigResolver,
    PluginLoader,
    PipelineExecutor,
    ProcessingContext,
    State,
    CoverChoice,
)


class VerbosityLevel:
    """Verbosity levels."""
    QUIET = 0    # Errors only
    NORMAL = 1   # Progress + warnings
    VERBOSE = 2  # Detailed info
    DEBUG = 3    # Everything


class WebServerPlugin:
    """Web server plugin with REST API and dynamic Jinja2 Web UI."""

    def __init__(self, config: dict | None = None) -> None:
        """Initialize web server plugin.

        Args:
            config: Plugin configuration
        """
        if not HAS_FASTAPI:
            raise ImportError(
                "FastAPI not installed. Install with: pip install fastapi uvicorn python-multipart websockets jinja2"
            )

        self.config = config or {}
        self.verbosity = VerbosityLevel.NORMAL
        self.host = self.config.get("host", "0.0.0.0")
        
        # Use random port >45000 if not specified
        self.port = self.config.get("port") or random.randint(45001, 65535)
        
        self.reload = self.config.get("reload", False)
        self.upload_dir = Path(self.config.get("upload_dir", "/tmp/audiomason/uploads"))
        self.upload_dir.mkdir(parents=True, exist_ok=True)

        # Active processing contexts
        self.contexts: dict[str, ProcessingContext] = {}
        self.websocket_clients: list[WebSocket] = []

        # Plugin loader reference (set by CLI)
        self.plugin_loader: PluginLoader | None = None

        # Create FastAPI app
        self.app = self._create_app()

    def _create_app(self) -> FastAPI:
        """Create FastAPI application.

        Returns:
            FastAPI app
        """
        app = FastAPI(
            title="AudioMason API",
            description="REST API for AudioMason audiobook processing",
            version="2.0.0",
        )

        # Setup Jinja2 templates
        templates_dir = Path(__file__).parent / "templates"
        self.templates = Jinja2Templates(directory=str(templates_dir))

        # Mount static files
        static_dir = Path(__file__).parent / "static"
        if static_dir.exists():
            app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        # HTML Routes (Web UI)
        app.get("/", response_class=HTMLResponse)(self.index)
        app.get("/plugins", response_class=HTMLResponse)(self.plugins_page)
        app.get("/config", response_class=HTMLResponse)(self.config_page)
        app.get("/jobs", response_class=HTMLResponse)(self.jobs_page)
        app.get("/wizards", response_class=HTMLResponse)(self.wizards_page)
        
        # API Routes (JSON)
        app.get("/api/status")(self.get_status)
        app.get("/api/config")(self.get_config)
        app.post("/api/config")(self.update_config)
        app.get("/api/plugins")(self.list_plugins_api)
        app.get("/api/wizards")(self.list_wizards_api)
        app.get("/api/jobs")(self.list_jobs)
        app.get("/api/jobs/{job_id}")(self.get_job)
        app.post("/api/upload")(self.upload_file)
        app.post("/api/process")(self.start_processing)
        app.delete("/api/jobs/{job_id}")(self.cancel_job)
        app.get("/api/checkpoints")(self.list_checkpoints)
        app.post("/api/checkpoints/{checkpoint_id}/resume")(self.resume_checkpoint)
        app.websocket("/ws")(self.websocket_endpoint)

        return app

    async def run(self) -> None:
        """Run web server - main entry point."""
        if self.verbosity >= VerbosityLevel.NORMAL:
            print("🌐 AudioMason Web Server")
            print()
            print(f"   Host: {self.host}")
            print(f"   Port: {self.port}")
            print(f"   URL:  http://localhost:{self.port}")
            print()
            print("Press Ctrl+C to stop")
            print()

        # Run uvicorn server
        log_level = "critical" if self.verbosity == VerbosityLevel.QUIET else \
                    "error" if self.verbosity == VerbosityLevel.NORMAL else \
                    "info" if self.verbosity == VerbosityLevel.VERBOSE else "debug"
        
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            reload=self.reload,
            log_level=log_level,
        )
        server = uvicorn.Server(config)
        await server.serve()

    # ═══════════════════════════════════════════
    #  WEB UI ENDPOINTS (HTML)
    # ═══════════════════════════════════════════

    async def index(self, request: Request) -> HTMLResponse:
        """Serve web UI homepage."""
        # Get system status
        status = await self._get_system_status()
        
        return self.templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "status": status,
                "active_jobs": len(self.contexts),
            }
        )

    async def plugins_page(self, request: Request) -> HTMLResponse:
        """Serve plugins management page."""
        plugins = await self._get_plugins_list()
        
        return self.templates.TemplateResponse(
            "plugins.html",
            {
                "request": request,
                "plugins": plugins,
            }
        )

    async def config_page(self, request: Request) -> HTMLResponse:
        """Serve configuration page."""
        config = await self._get_config_dict()
        
        return self.templates.TemplateResponse(
            "config.html",
            {
                "request": request,
                "config": config,
            }
        )

    async def jobs_page(self, request: Request) -> HTMLResponse:
        """Serve jobs monitoring page."""
        jobs = await self._get_jobs_list()
        
        return self.templates.TemplateResponse(
            "jobs.html",
            {
                "request": request,
                "jobs": jobs,
            }
        )

    async def wizards_page(self, request: Request) -> HTMLResponse:
        """Serve wizards page."""
        wizards = await self._get_wizards_list()
        
        return self.templates.TemplateResponse(
            "wizards.html",
            {
                "request": request,
                "wizards": wizards,
            }
        )

    # ═══════════════════════════════════════════
    #  API ENDPOINTS (JSON)
    # ═══════════════════════════════════════════

    async def get_status(self) -> JSONResponse:
        """Get system status."""
        status = await self._get_system_status()
        return JSONResponse(status)

    async def get_config(self) -> JSONResponse:
        """Get current configuration."""
        config = await self._get_config_dict()
        return JSONResponse(config)

    async def update_config(self, config_data: dict) -> JSONResponse:
        """Update configuration.

        Args:
            config_data: New config values
        """
        # TODO: Implement config update with validation
        return JSONResponse({"message": "Config updated", "data": config_data})

    async def list_plugins_api(self) -> JSONResponse:
        """List all plugins (API)."""
        plugins = await self._get_plugins_list()
        return JSONResponse(plugins)

    async def list_wizards_api(self) -> JSONResponse:
        """List all wizards (API)."""
        wizards = await self._get_wizards_list()
        return JSONResponse(wizards)

    async def list_jobs(self) -> JSONResponse:
        """List all processing jobs."""
        jobs = await self._get_jobs_list()
        return JSONResponse(jobs)

    async def get_job(self, job_id: str) -> JSONResponse:
        """Get job details.

        Args:
            job_id: Job ID
        """
        if job_id not in self.contexts:
            return JSONResponse({"error": "Job not found"}, status_code=404)
        
        ctx = self.contexts[job_id]
        return JSONResponse({
            "id": ctx.id,
            "source": str(ctx.source),
            "title": ctx.title,
            "author": ctx.author,
            "year": ctx.year,
            "state": ctx.state.value,
            "progress": ctx.progress,
            "current_step": ctx.current_step,
            "completed_steps": ctx.completed_steps,
            "warnings": ctx.warnings,
            "timings": ctx.timings,
        })

    async def upload_file(
        self,
        file: UploadFile = File(...),
    ) -> JSONResponse:
        """Upload audio file.

        Args:
            file: Uploaded file
        """
        # Save uploaded file
        file_path = self.upload_dir / file.filename
        
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        return JSONResponse({
            "message": "File uploaded",
            "filename": file.filename,
            "path": str(file_path),
            "size": len(content),
        })

    async def start_processing(
        self,
        filename: str = Form(...),
        author: str = Form(...),
        title: str = Form(...),
        year: int = Form(None),
        bitrate: str = Form("128k"),
        loudnorm: bool = Form(False),
        split_chapters: bool = Form(False),
        pipeline: str = Form("standard"),
    ) -> JSONResponse:
        """Start processing a file.

        Args:
            filename: Uploaded filename
            author: Book author
            title: Book title
            year: Publication year
            bitrate: Audio bitrate
            loudnorm: Enable loudness normalization
            split_chapters: Split by chapters
            pipeline: Pipeline to use
        """
        file_path = self.upload_dir / filename
        
        if not file_path.exists():
            return JSONResponse({"error": "File not found"}, status_code=404)
        
        # Create context
        ctx = ProcessingContext(
            id=str(uuid.uuid4()),
            source=file_path,
            author=author,
            title=title,
            year=year,
            state=State.PROCESSING,
            loudnorm=loudnorm,
            split_chapters=split_chapters,
            target_bitrate=bitrate,
        )
        
        self.contexts[ctx.id] = ctx
        
        # Start processing in background
        asyncio.create_task(self._process_book(ctx, pipeline))
        
        return JSONResponse({
            "message": "Processing started",
            "job_id": ctx.id,
        })

    async def cancel_job(self, job_id: str) -> JSONResponse:
        """Cancel processing job.

        Args:
            job_id: Job ID
        """
        if job_id in self.contexts:
            ctx = self.contexts[job_id]
            ctx.state = State.INTERRUPTED
            return JSONResponse({"message": "Job cancelled"})
        
        return JSONResponse({"error": "Job not found"}, status_code=404)

    async def list_checkpoints(self) -> JSONResponse:
        """List available checkpoints."""
        from audiomason.checkpoint import CheckpointManager
        
        manager = CheckpointManager()
        checkpoints = manager.list_checkpoints()
        
        return JSONResponse(checkpoints)

    async def resume_checkpoint(self, checkpoint_id: str) -> JSONResponse:
        """Resume from checkpoint.

        Args:
            checkpoint_id: Checkpoint ID
        """
        from audiomason.checkpoint import CheckpointManager
        
        manager = CheckpointManager()
        
        try:
            ctx = manager.load_checkpoint(checkpoint_id)
            self.contexts[ctx.id] = ctx
            
            # Resume processing
            asyncio.create_task(self._process_book(ctx, "standard"))
            
            return JSONResponse({
                "message": "Processing resumed",
                "job_id": ctx.id,
            })
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    async def websocket_endpoint(self, websocket: WebSocket) -> None:
        """WebSocket endpoint for real-time updates.

        Args:
            websocket: WebSocket connection
        """
        await websocket.accept()
        self.websocket_clients.append(websocket)
        
        try:
            while True:
                # Send status updates
                await websocket.send_json({
                    "type": "status",
                    "active_jobs": len(self.contexts),
                })
                await asyncio.sleep(1)
        except WebSocketDisconnect:
            self.websocket_clients.remove(websocket)

    # ═══════════════════════════════════════════
    #  INTERNAL HELPER METHODS
    # ═══════════════════════════════════════════

    async def _get_system_status(self) -> dict[str, Any]:
        """Get comprehensive system status.

        Returns:
            System status dictionary
        """
        return {
            "status": "running",
            "version": "2.0.0",
            "active_jobs": len(self.contexts),
            "total_plugins": len(self.plugin_loader.list_plugins()) if self.plugin_loader else 0,
            "uptime": "N/A",  # TODO: Implement uptime tracking
        }

    async def _get_plugins_list(self) -> list[dict[str, Any]]:
        """Get list of all plugins with details.

        Returns:
            List of plugin dictionaries
        """
        if not self.plugin_loader:
            return []
        
        plugins = []
        for plugin_name in self.plugin_loader.list_plugins():
            manifest = self.plugin_loader.get_manifest(plugin_name)
            if manifest:
                plugins.append({
                    "name": manifest.name,
                    "version": manifest.version,
                    "description": manifest.description,
                    "author": manifest.author,
                    "interfaces": manifest.interfaces,
                    "enabled": True,  # TODO: Track enabled state
                })
        
        return plugins

    async def _get_config_dict(self) -> dict[str, Any]:
        """Get current configuration as dictionary.

        Returns:
            Configuration dictionary with values and sources
        """
        resolver = ConfigResolver()
        all_config = resolver.resolve_all()
        
        return {
            key: {"value": source.value, "source": source.source}
            for key, source in all_config.items()
        }

    async def _get_jobs_list(self) -> list[dict[str, Any]]:
        """Get list of all processing jobs.

        Returns:
            List of job dictionaries
        """
        jobs = []
        for ctx_id, ctx in self.contexts.items():
            jobs.append({
                "id": ctx_id,
                "title": ctx.title,
                "author": ctx.author,
                "state": ctx.state.value,
                "progress": ctx.progress,
                "current_step": ctx.current_step,
            })
        
        return jobs

    async def _get_wizards_list(self) -> list[dict[str, Any]]:
        """Get list of available wizards.

        Returns:
            List of wizard dictionaries
        """
        # TODO: Implement wizard discovery
        wizards_dir = Path(__file__).parent.parent.parent / "wizards"
        wizards = []
        
        if wizards_dir.exists():
            for wizard_file in wizards_dir.glob("*.yaml"):
                wizards.append({
                    "name": wizard_file.stem,
                    "file": wizard_file.name,
                    "path": str(wizard_file),
                })
        
        return wizards

    async def _process_book(self, context: ProcessingContext, pipeline_name: str) -> None:
        """Process book in background.

        Args:
            context: Processing context
            pipeline_name: Pipeline to use
        """
        try:
            # Load plugins
            plugins_dir = Path(__file__).parent.parent
            loader = PluginLoader(builtin_plugins_dir=plugins_dir)
            
            # Load required plugins
            for plugin in ["audio_processor", "file_io"]:
                plugin_dir = plugins_dir / plugin
                if plugin_dir.exists():
                    loader.load_plugin(plugin_dir, validate=False)
            
            # Execute pipeline
            pipeline_path = plugins_dir.parent / "pipelines" / f"{pipeline_name}.yaml"
            executor = PipelineExecutor(loader)
            
            result = await executor.execute_from_yaml(pipeline_path, context)
            
            # Update context
            self.contexts[context.id] = result
            
            # Broadcast to websockets
            await self._broadcast_update(context.id, "complete")
            
        except Exception as e:
            context.state = State.ERROR
            context.add_error(e)
            await self._broadcast_update(context.id, "error")

    async def _broadcast_update(self, job_id: str, event_type: str) -> None:
        """Broadcast update to all websocket clients.

        Args:
            job_id: Job ID
            event_type: Event type
        """
        if not self.websocket_clients:
            return
        
        ctx = self.contexts.get(job_id)
        if not ctx:
            return
        
        message = {
            "type": "job_update",
            "event": event_type,
            "job_id": job_id,
            "progress": ctx.progress,
            "state": ctx.state.value,
        }
        
        for client in self.websocket_clients:
            try:
                await client.send_json(message)
            except Exception:
                pass
