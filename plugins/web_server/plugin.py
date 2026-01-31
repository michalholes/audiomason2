"""Web Server plugin - FastAPI REST API + Jinja2 Web UI.

Provides complete web interface for AudioMason control with dynamic templates.
"""

from __future__ import annotations

import asyncio
import json
import uuid
import shutil
import zipfile
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
            config: Plugin configuration (legacy, prefer config_resolver)
        """
        if not HAS_FASTAPI:
            raise ImportError(
                "FastAPI not installed. Install with: pip install fastapi uvicorn python-multipart websockets jinja2"
            )

        self.config = config or {}
        self.verbosity = VerbosityLevel.NORMAL
        
        # Will be set by CLI
        self.config_resolver: ConfigResolver | None = None
        self.plugin_loader: PluginLoader | None = None
        
        # Lazy init - set in run()
        self.host: str = "0.0.0.0"
        self.port: int = 8080
        self.upload_dir: Path = Path("/tmp/audiomason/uploads")

        # Active processing contexts
        self.contexts: dict[str, ProcessingContext] = {}
        self.websocket_clients: list[WebSocket] = []

        # Create FastAPI app
        self.app = self._create_app()

    def _resolve_config(self) -> None:
        """Resolve configuration from ConfigResolver."""
        if not self.config_resolver:
            # Fallback to defaults
            self.host = "0.0.0.0"
            self.port = 8080
            self.upload_dir = Path("/tmp/audiomason/uploads")
            if self.verbosity >= VerbosityLevel.DEBUG:
                print(f"[DEBUG] No ConfigResolver, using defaults")
            return
        
        # Resolve web.host
        try:
            self.host, source = self.config_resolver.resolve("web.host")
            if self.verbosity >= VerbosityLevel.VERBOSE:
                print(f"  Host: {self.host} (source: {source})")
        except Exception as e:
            self.host = "0.0.0.0"
            if self.verbosity >= VerbosityLevel.DEBUG:
                print(f"[DEBUG] Failed to resolve web.host: {e}, using default")
        
        # Resolve web.port
        try:
            self.port, source = self.config_resolver.resolve("web.port")
            if self.verbosity >= VerbosityLevel.VERBOSE:
                print(f"  Port: {self.port} (source: {source})")
        except Exception as e:
            import random
            self.port = random.randint(45001, 65535)
            if self.verbosity >= VerbosityLevel.DEBUG:
                print(f"[DEBUG] Failed to resolve web.port: {e}")
                print(f"[DEBUG] Using random port: {self.port}")
        
        # Resolve upload_dir
        try:
            upload_dir_str, source = self.config_resolver.resolve("web.upload_dir")
            self.upload_dir = Path(upload_dir_str)
            if self.verbosity >= VerbosityLevel.VERBOSE:
                print(f"  Upload dir: {self.upload_dir} (source: {source})")
        except Exception as e:
            self.upload_dir = Path("/tmp/audiomason/uploads")
            if self.verbosity >= VerbosityLevel.DEBUG:
                print(f"[DEBUG] Failed to resolve web.upload_dir: {e}, using default")
        
        # Create upload directory
        self.upload_dir.mkdir(parents=True, exist_ok=True)

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

        # ===== HTML ROUTES (Web UI) =====
        app.get("/", response_class=HTMLResponse)(self.index)
        app.get("/plugins", response_class=HTMLResponse)(self.plugins_page)
        app.get("/config", response_class=HTMLResponse)(self.config_page)
        app.get("/jobs", response_class=HTMLResponse)(self.jobs_page)
        app.get("/wizards", response_class=HTMLResponse)(self.wizards_page)
        
        # ===== API ROUTES (JSON) =====
        # Status & Config
        app.get("/api/status")(self.get_status)
        app.get("/api/config")(self.get_config)
        app.post("/api/config")(self.update_config)
        
        # Plugins
        app.get("/api/plugins")(self.list_plugins_api)
        app.put("/api/plugins/{name}/enable")(self.enable_plugin)
        app.put("/api/plugins/{name}/disable")(self.disable_plugin)
        app.delete("/api/plugins/{name}")(self.delete_plugin)
        app.get("/api/plugins/{name}/config")(self.get_plugin_config)
        app.post("/api/plugins/{name}/config")(self.save_plugin_config)
        app.post("/api/plugins/install")(self.install_plugin)
        
        # Wizards
        app.get("/api/wizards")(self.list_wizards_api)
        app.get("/api/wizards/{name}")(self.get_wizard)
        app.post("/api/wizards/{name}/run")(self.run_wizard)
        app.post("/api/wizards/create")(self.create_wizard)
        app.put("/api/wizards/{name}")(self.update_wizard)
        app.delete("/api/wizards/{name}")(self.delete_wizard)
        
        # Jobs
        app.get("/api/jobs")(self.list_jobs)
        app.get("/api/jobs/{job_id}")(self.get_job)
        app.post("/api/upload")(self.upload_files)
        app.post("/api/process")(self.start_processing)
        app.delete("/api/jobs/{job_id}")(self.cancel_job)
        
        # Checkpoints
        app.get("/api/checkpoints")(self.list_checkpoints)
        app.post("/api/checkpoints/{checkpoint_id}/resume")(self.resume_checkpoint)
        
        # WebSocket
        app.websocket("/ws")(self.websocket_endpoint)

        return app

    async def run(self) -> None:
        """Run web server - main entry point."""
        # Resolve configuration
        self._resolve_config()
        
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
                    "info" if self.verbosity == VerbosityLevel.VERBOSE else \
                    "debug"

        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level=log_level,
            access_log=(self.verbosity >= VerbosityLevel.VERBOSE),
        )
        server = uvicorn.Server(config)
        await server.serve()

    # ═══════════════════════════════════════════
    #  HTML PAGES
    # ═══════════════════════════════════════════

    async def index(self, request: Request) -> HTMLResponse:
        """Serve homepage/dashboard."""
        status = await self._get_system_status()
        jobs = await self._get_jobs_list()
        
        return self.templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "status": status,
                "jobs": jobs,
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
    #  API ENDPOINTS - STATUS & CONFIG
    # ═══════════════════════════════════════════

    async def get_status(self) -> JSONResponse:
        """Get system status."""
        status = await self._get_system_status()
        return JSONResponse(status)

    async def get_config(self) -> JSONResponse:
        """Get current configuration."""
        config = await self._get_config_dict()
        return JSONResponse(config)

    async def update_config(self, request: Request) -> JSONResponse:
        """Update configuration (saves to user config file)."""
        try:
            data = await request.json()
            
            if self.verbosity >= VerbosityLevel.DEBUG:
                print(f"[DEBUG] Config save request")
                print(f"[DEBUG]   Data keys: {list(data.keys())}")
            
            # Get user config path
            config_path = Path.home() / ".config" / "audiomason" / "config.yaml"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            if self.verbosity >= VerbosityLevel.DEBUG:
                print(f"[DEBUG]   Config path: {config_path}")
            
            # Load existing config or start fresh
            existing = {}
            if config_path.exists():
                import yaml
                with open(config_path) as f:
                    existing = yaml.safe_load(f) or {}
                if self.verbosity >= VerbosityLevel.DEBUG:
                    print(f"[DEBUG]   Loaded existing config with {len(existing)} keys")
            
            # Update with new values (nested merge)
            def merge_dict(base: dict, updates: dict) -> dict:
                """Recursively merge dictionaries."""
                result = base.copy()
                for key, value in updates.items():
                    if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                        result[key] = merge_dict(result[key], value)
                    else:
                        result[key] = value
                return result
            
            updated = merge_dict(existing, data)
            
            if self.verbosity >= VerbosityLevel.DEBUG:
                print(f"[DEBUG]   Merged config has {len(updated)} keys")
            
            # Save to YAML
            import yaml
            with open(config_path, 'w') as f:
                yaml.dump(updated, f, default_flow_style=False, allow_unicode=True)
            
            if self.verbosity >= VerbosityLevel.DEBUG:
                print(f"[DEBUG]   ✓ Saved to {config_path}")
            
            return JSONResponse({
                "message": "Configuration saved successfully",
                "path": str(config_path),
                "config": updated,
            })
        except Exception as e:
            if self.verbosity >= VerbosityLevel.DEBUG:
                print(f"[DEBUG] ERROR saving config: {e}")
                import traceback
                traceback.print_exc()
            return JSONResponse({
                "error": f"Failed to save configuration: {str(e)}"
            }, status_code=500)

    # ═══════════════════════════════════════════
    #  API ENDPOINTS - PLUGINS
    # ═══════════════════════════════════════════

    async def list_plugins_api(self) -> JSONResponse:
        """List all plugins (API)."""
        plugins = await self._get_plugins_list()
        return JSONResponse(plugins)

    async def enable_plugin(self, name: str) -> JSONResponse:
        """Enable plugin."""
        # TODO: Implement plugin enable/disable tracking
        return JSONResponse({"message": f"Plugin '{name}' enabled"})

    async def disable_plugin(self, name: str) -> JSONResponse:
        """Disable plugin."""
        # TODO: Implement plugin enable/disable tracking
        return JSONResponse({"message": f"Plugin '{name}' disabled"})

    async def delete_plugin(self, name: str) -> JSONResponse:
        """Delete plugin."""
        if not self.plugin_loader:
            return JSONResponse({"error": "Plugin loader not available"}, status_code=500)
        
        # TODO: Implement plugin deletion
        return JSONResponse({"message": f"Plugin '{name}' deleted"})

    async def get_plugin_config(self, name: str) -> JSONResponse:
        """Get plugin configuration."""
        # TODO: Load plugin config from config file
        return JSONResponse({})

    async def save_plugin_config(self, name: str, request: Request) -> JSONResponse:
        """Save plugin configuration."""
        data = await request.json()
        
        # TODO: Save plugin config to config file
        return JSONResponse({"message": f"Config for '{name}' saved"})

    async def install_plugin(
        self,
        files: list[UploadFile] = File(None),
        url: str = Form(None),
    ) -> JSONResponse:
        """Install plugin from ZIP or URL."""
        if files:
            # Install from uploaded ZIP
            for file in files:
                if not file.filename.endswith('.zip'):
                    continue
                
                # Save ZIP
                zip_path = self.upload_dir / file.filename
                with open(zip_path, "wb") as f:
                    content = await file.read()
                    f.write(content)
                
                # Extract to plugins directory
                plugins_dir = Path(__file__).parent.parent
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(plugins_dir)
                
                # Clean up
                zip_path.unlink()
                
                return JSONResponse({"message": f"Plugin installed from {file.filename}"})
        
        elif url:
            # TODO: Download from URL and install
            return JSONResponse({"message": f"Plugin installed from {url}"})
        
        return JSONResponse({"error": "No file or URL provided"}, status_code=400)

    # ═══════════════════════════════════════════
    #  API ENDPOINTS - WIZARDS
    # ═══════════════════════════════════════════

    async def list_wizards_api(self) -> JSONResponse:
        """List all wizards (API)."""
        wizards = await self._get_wizards_list()
        return JSONResponse(wizards)

    async def get_wizard(self, name: str) -> JSONResponse:
        """Get wizard details."""
        wizards_dir = Path(__file__).parent.parent.parent / "wizards"
        wizard_file = wizards_dir / f"{name}.yaml"
        
        if not wizard_file.exists():
            return JSONResponse({"error": "Wizard not found"}, status_code=404)
        
        import yaml
        with open(wizard_file) as f:
            wizard_data = yaml.safe_load(f)
        
        return JSONResponse(wizard_data)

    async def run_wizard(self, name: str, request: Request) -> JSONResponse:
        """Run wizard with provided inputs."""
        data = await request.json()
        
        # TODO: Integrate with WizardEngine when implemented
        return JSONResponse({"message": f"Wizard '{name}' started", "job_id": str(uuid.uuid4())})

    async def create_wizard(self, request: Request) -> JSONResponse:
        """Create new wizard."""
        data = await request.json()
        name = data.get("name")
        content = data.get("content")
        
        if not name or not content:
            return JSONResponse({"error": "Name and content required"}, status_code=400)
        
        wizards_dir = Path(__file__).parent.parent.parent / "wizards"
        wizards_dir.mkdir(parents=True, exist_ok=True)
        
        wizard_file = wizards_dir / f"{name}.yaml"
        with open(wizard_file, "w") as f:
            f.write(content)
        
        return JSONResponse({"message": f"Wizard '{name}' created"})

    async def update_wizard(self, name: str, request: Request) -> JSONResponse:
        """Update wizard YAML."""
        data = await request.json()
        content = data.get("content")
        
        if not content:
            return JSONResponse({"error": "Content required"}, status_code=400)
        
        wizards_dir = Path(__file__).parent.parent.parent / "wizards"
        wizard_file = wizards_dir / f"{name}.yaml"
        
        if not wizard_file.exists():
            return JSONResponse({"error": "Wizard not found"}, status_code=404)
        
        with open(wizard_file, "w") as f:
            f.write(content)
        
        return JSONResponse({"message": f"Wizard '{name}' updated"})

    async def delete_wizard(self, name: str) -> JSONResponse:
        """Delete wizard."""
        wizards_dir = Path(__file__).parent.parent.parent / "wizards"
        wizard_file = wizards_dir / f"{name}.yaml"
        
        if not wizard_file.exists():
            return JSONResponse({"error": "Wizard not found"}, status_code=404)
        
        wizard_file.unlink()
        
        return JSONResponse({"message": f"Wizard '{name}' deleted"})

    # ═══════════════════════════════════════════
    #  API ENDPOINTS - JOBS
    # ═══════════════════════════════════════════

    async def list_jobs(self) -> JSONResponse:
        """List all processing jobs."""
        jobs = await self._get_jobs_list()
        return JSONResponse(jobs)

    async def get_job(self, job_id: str) -> JSONResponse:
        """Get job details."""
        if job_id not in self.contexts:
            return JSONResponse({"error": "Job not found"}, status_code=404)
        
        ctx = self.contexts[job_id]
        return JSONResponse({
            "id": ctx.id,
            "source": str(ctx.source),
            "title": ctx.title,
            "author": ctx.author,
            "state": ctx.state.value,
            "progress": ctx.progress,
            "current_step": ctx.current_step,
        })

    async def upload_files(
        self,
        files: list[UploadFile] = File(...),
    ) -> JSONResponse:
        """Upload multiple audio files or ZIP archives.

        Args:
            files: List of uploaded files
        """
        if self.verbosity >= VerbosityLevel.DEBUG:
            print(f"[DEBUG] Upload request: {len(files)} file(s)")
        
        uploaded = []
        errors = []
        
        for file in files:
            try:
                file_path = self.upload_dir / file.filename
                
                if self.verbosity >= VerbosityLevel.DEBUG:
                    print(f"[DEBUG] Processing file: {file.filename}")
                
                # Save file
                with open(file_path, "wb") as f:
                    content = await file.read()
                    f.write(content)
                
                if self.verbosity >= VerbosityLevel.DEBUG:
                    print(f"[DEBUG] Saved {len(content)} bytes to {file_path}")
                
                # If ZIP, extract it
                if file.filename.endswith('.zip'):
                    extract_dir = self.upload_dir / file.filename.replace('.zip', '')
                    extract_dir.mkdir(exist_ok=True)
                    
                    if self.verbosity >= VerbosityLevel.DEBUG:
                        print(f"[DEBUG] Extracting ZIP to {extract_dir}")
                    
                    with zipfile.ZipFile(file_path, 'r') as zip_ref:
                        zip_ref.extractall(extract_dir)
                    
                    # Remove ZIP after extraction
                    file_path.unlink()
                    
                    # Find audio files in extracted directory
                    audio_files = []
                    for ext in ['*.mp3', '*.m4a', '*.m4b', '*.opus']:
                        audio_files.extend(extract_dir.glob(f"**/{ext}"))
                    
                    if self.verbosity >= VerbosityLevel.DEBUG:
                        print(f"[DEBUG] Found {len(audio_files)} audio files in ZIP")
                    
                    uploaded.extend([str(f) for f in audio_files])
                else:
                    uploaded.append(str(file_path))
            except Exception as e:
                error_msg = f"Failed to process {file.filename}: {str(e)}"
                errors.append(error_msg)
                if self.verbosity >= VerbosityLevel.DEBUG:
                    print(f"[DEBUG] ERROR: {error_msg}")
                    import traceback
                    traceback.print_exc()
        
        if errors:
            return JSONResponse({
                "error": "Some files failed to upload",
                "details": errors,
                "uploaded": len(uploaded),
                "files": uploaded,
            }, status_code=207)  # Multi-Status
        
        return JSONResponse({
            "message": f"Uploaded {len(uploaded)} file(s)",
            "files": uploaded,
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
        """Start processing a file."""
        # Create context
        ctx = ProcessingContext(
            id=str(uuid.uuid4()),
            source=Path(filename),
            author=author,
            title=title,
            year=year,
            state=State.INIT,
        )
        
        self.contexts[ctx.id] = ctx
        
        # TODO: Start processing in background
        
        return JSONResponse({
            "message": "Processing started",
            "job_id": ctx.id,
        })

    async def cancel_job(self, job_id: str) -> JSONResponse:
        """Cancel processing job."""
        if job_id not in self.contexts:
            return JSONResponse({"error": "Job not found"}, status_code=404)
        
        # TODO: Implement job cancellation
        del self.contexts[job_id]
        
        return JSONResponse({"message": "Job cancelled"})

    # ═══════════════════════════════════════════
    #  API ENDPOINTS - CHECKPOINTS
    # ═══════════════════════════════════════════

    async def list_checkpoints(self) -> JSONResponse:
        """List available checkpoints."""
        # TODO: Implement checkpoint listing
        return JSONResponse([])

    async def resume_checkpoint(self, checkpoint_id: str) -> JSONResponse:
        """Resume from checkpoint."""
        # TODO: Implement checkpoint resume
        return JSONResponse({"message": f"Resumed checkpoint {checkpoint_id}"})

    # ═══════════════════════════════════════════
    #  WEBSOCKET
    # ═══════════════════════════════════════════

    async def websocket_endpoint(self, websocket: WebSocket) -> None:
        """WebSocket endpoint for real-time updates."""
        await websocket.accept()
        self.websocket_clients.append(websocket)
        
        try:
            while True:
                # Keep connection alive
                await websocket.receive_text()
        except WebSocketDisconnect:
            self.websocket_clients.remove(websocket)

    # ═══════════════════════════════════════════
    #  HELPER METHODS
    # ═══════════════════════════════════════════

    async def _get_system_status(self) -> dict[str, Any]:
        """Get system status."""
        return {
            "status": "running",
            "active_jobs": len(self.contexts),
            "version": "2.0.0",
            "plugins_loaded": len(await self._get_plugins_list()),
            "wizards_available": len(await self._get_wizards_list()),
        }

    async def _get_plugins_list(self) -> list[dict[str, Any]]:
        """Get list of all plugins with details."""
        if not self.plugin_loader:
            if self.verbosity >= VerbosityLevel.DEBUG:
                print(f"[DEBUG] No plugin_loader set")
            return []
        
        if self.verbosity >= VerbosityLevel.DEBUG:
            print(f"[DEBUG] Getting plugin list from loader")
        
        plugins = []
        plugin_names = self.plugin_loader.list_plugins()
        
        if self.verbosity >= VerbosityLevel.DEBUG:
            print(f"[DEBUG] Found {len(plugin_names)} plugins: {plugin_names}")
        
        for plugin_name in plugin_names:
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
                if self.verbosity >= VerbosityLevel.DEBUG:
                    print(f"[DEBUG] Added plugin: {manifest.name}")
            else:
                if self.verbosity >= VerbosityLevel.DEBUG:
                    print(f"[DEBUG] No manifest for plugin: {plugin_name}")
        
        return plugins

    async def _get_config_dict(self) -> dict[str, Any]:
        """Get current configuration as dictionary."""
        if not self.config_resolver:
            return {}
        
        all_config = self.config_resolver.resolve_all()
        
        return {
            key: {"value": source.value, "source": source.source}
            for key, source in all_config.items()
        }

    async def _get_jobs_list(self) -> list[dict[str, Any]]:
        """Get list of all processing jobs."""
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
        """Get list of available wizards."""
        wizards_dir = Path(__file__).parent.parent.parent / "wizards"
        
        if self.verbosity >= VerbosityLevel.DEBUG:
            print(f"[DEBUG] Looking for wizards in: {wizards_dir}")
        
        if not wizards_dir.exists():
            if self.verbosity >= VerbosityLevel.DEBUG:
                print(f"[DEBUG] Wizards directory does not exist")
            return []
        
        wizards = []
        yaml_files = list(wizards_dir.glob("*.yaml"))
        
        if self.verbosity >= VerbosityLevel.DEBUG:
            print(f"[DEBUG] Found {len(yaml_files)} YAML files")
        
        for yaml_file in yaml_files:
            import yaml
            try:
                with open(yaml_file) as f:
                    wizard_data = yaml.safe_load(f)
                
                if self.verbosity >= VerbosityLevel.DEBUG:
                    print(f"[DEBUG] Parsing wizard: {yaml_file.stem}")
                    print(f"[DEBUG]   Raw keys: {list(wizard_data.keys())}")
                
                # Handle nested structure: wizard_data may have 'wizard' root key
                if 'wizard' in wizard_data:
                    wizard = wizard_data['wizard']
                    if self.verbosity >= VerbosityLevel.DEBUG:
                        print(f"[DEBUG]   Found nested 'wizard' key")
                        print(f"[DEBUG]   Wizard keys: {list(wizard.keys())}")
                else:
                    wizard = wizard_data
                    if self.verbosity >= VerbosityLevel.DEBUG:
                        print(f"[DEBUG]   Using flat structure")
                
                steps = wizard.get("steps", [])
                if not isinstance(steps, list):
                    if self.verbosity >= VerbosityLevel.DEBUG:
                        print(f"[DEBUG]   WARNING: steps is not a list: {type(steps)}")
                    steps = []
                else:
                    if self.verbosity >= VerbosityLevel.DEBUG:
                        print(f"[DEBUG]   Found {len(steps)} steps")
                
                wizards.append({
                    "name": yaml_file.stem,
                    "title": wizard.get("name", yaml_file.stem),
                    "description": wizard.get("description", ""),
                    "steps": len(steps),
                })
                
                if self.verbosity >= VerbosityLevel.DEBUG:
                    print(f"[DEBUG]   ✓ Added wizard '{wizard.get('name', yaml_file.stem)}' with {len(steps)} steps")
            except Exception as e:
                if self.verbosity >= VerbosityLevel.DEBUG:
                    print(f"[DEBUG] ✗ Failed to parse {yaml_file.stem}: {e}")
                    import traceback
                    traceback.print_exc()
                continue
        
        return wizards
