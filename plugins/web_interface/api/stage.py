from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from ..util.fs import find_repo_root
from ..util.paths import stage_dir_from_config
from ._am_cfg import get_inbox_dir, read_am_config_text


def _stage_dir() -> Path:
    repo = find_repo_root()
    txt = read_am_config_text()
    inbox = get_inbox_dir(txt)
    d = stage_dir_from_config(inbox, repo)
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
        files: list[UploadFile] = File(...),
        relpaths: list[str] | None = Form(default=None),
    ) -> dict[str, Any]:
        d = _stage_dir()
        if relpaths is None:
            relpaths = [f.filename or "upload.bin" for f in files]
        if len(relpaths) != len(files):
            raise HTTPException(status_code=400, detail="relpaths length mismatch")

        saved = 0
        for up, rel in zip(files, relpaths):
            rel = rel.lstrip("/").replace("..", "_")
            out = (d / rel).resolve()
            if d not in out.parents and out != d:
                raise HTTPException(status_code=400, detail="invalid path")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(await up.read())
            saved += 1
        return {"ok": True, "saved": saved}
