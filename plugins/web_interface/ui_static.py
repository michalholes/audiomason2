from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_ui_static(app: FastAPI) -> None:
    ui_dir = Path(__file__).resolve().parent / "ui"
    index = ui_dir / "index.html"

    # Serve static assets under /ui
    app.mount("/ui", StaticFiles(directory=str(ui_dir), html=True), name="ui")

    @app.get("/")
    def ui_root() -> FileResponse:
        return FileResponse(str(index), headers={"Cache-Control": "no-store"})

    # SPA fallback for any non-API path.
    @app.get("/{full_path:path}")
    def ui_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api/") or full_path.startswith("ui/"):
            # Let FastAPI 404 for missing API/assets
            raise HTTPException(status_code=404)
        return FileResponse(str(index), headers={"Cache-Control": "no-store"})
