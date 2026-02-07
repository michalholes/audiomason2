from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from audiomason.core.config_service import ConfigService


def _stage_dir() -> Path:
    svc = ConfigService()
    cfg = svc.get_config()
    inbox_dir = cfg.get("inbox_dir")
    if isinstance(inbox_dir, str) and inbox_dir.strip():
        base = Path(inbox_dir)
        d = base / "stage"
    else:
        d = Path.home() / ".audiomason/stage"
    d.mkdir(parents=True, exist_ok=True)
    return d


def mount_stage(app: FastAPI) -> None:
    @app.get("/api/stage")
    def list_stage() -> dict[str, Any]:
        d = _stage_dir()
        items: list[dict[str, Any]] = []
        for p in sorted(d.rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(d))
                items.append({"name": rel, "size": p.stat().st_size})
        return {"dir": str(d), "items": items}

    @app.delete("/api/stage/{name:path}")
    def delete_stage(name: str) -> dict[str, Any]:
        d = _stage_dir()
        target = (d / name).resolve()
        if d not in target.parents and target != d:
            raise HTTPException(status_code=400, detail="invalid path")
        if target.exists() and target.is_file():
            target.unlink()
            return {"ok": True}
        raise HTTPException(status_code=404, detail="not found")

    @app.post("/api/stage/upload")
    async def upload_stage(
        files: Annotated[list[UploadFile], File()],
        relpaths: Annotated[list[str] | None, Form()] = None,
    ) -> dict[str, Any]:
        d = _stage_dir()
        if relpaths is None:
            relpaths = [f.filename or "upload.bin" for f in files]
        if len(relpaths) != len(files):
            raise HTTPException(status_code=400, detail="relpaths length mismatch")

        saved = 0
        for up, rel in zip(files, relpaths, strict=True):
            rel = rel.lstrip("/").replace("..", "_")
            out = (d / rel).resolve()
            if d not in out.parents and out != d:
                raise HTTPException(status_code=400, detail="invalid path")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(await up.read())
            saved += 1
        return {"ok": True, "saved": saved}
