from __future__ import annotations

from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile

from audiomason.core.config import ConfigResolver
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName


def _resolver(request: Request) -> ConfigResolver:
    r = getattr(request.app.state, "config_resolver", None)
    if isinstance(r, ConfigResolver):
        return r
    return ConfigResolver()


def _fs(request: Request) -> FileService:
    fs = getattr(request.app.state, "file_service", None)
    if isinstance(fs, FileService):
        return fs
    fs = FileService.from_resolver(_resolver(request))
    request.app.state.file_service = fs
    return fs


def _debug(request: Request) -> bool:
    v = getattr(request.app.state, "verbosity", 1)
    return int(v) >= 3


def mount_stage(app: FastAPI) -> None:
    # Backward-compatible stage endpoints implemented via FileService.
    @app.get("/api/stage")
    def list_stage(request: Request) -> dict[str, Any]:
        fs = _fs(request)
        items: list[dict[str, Any]] = []
        for e in fs.list_dir(RootName.STAGE, ".", recursive=True):
            if e.is_dir:
                continue
            items.append(
                {
                    "name": e.rel_path,
                    "size": e.size,
                    "mtime_ts": int(e.mtime) if e.mtime is not None else None,
                }
            )
        out: dict[str, Any] = {"items": items, "dir": str(fs.root_dir(RootName.STAGE))}
        if _debug(request):
            out["root"] = RootName.STAGE.value
        return out

    @app.delete("/api/stage/{name:path}")
    def delete_stage(request: Request, name: str) -> dict[str, Any]:
        fs = _fs(request)
        rel = name.lstrip("/")
        try:
            fs.delete_file(RootName.STAGE, rel)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail="not found") from e
        return {"ok": True}

    @app.post("/api/stage/upload")
    async def upload_stage(
        request: Request,
        files: Annotated[list[UploadFile], File()],
        relpaths: Annotated[list[str] | None, Form()] = None,
    ) -> dict[str, Any]:
        fs = _fs(request)
        if relpaths is None:
            relpaths = [f.filename or "upload.bin" for f in files]
        if len(relpaths) != len(files):
            raise HTTPException(status_code=400, detail="relpaths length mismatch")

        saved = 0
        for up, rel in zip(files, relpaths, strict=True):
            rel = rel.lstrip("/")
            parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
            if parent:
                fs.mkdir(RootName.STAGE, parent, parents=True, exist_ok=True)
            with fs.open_write(RootName.STAGE, rel, overwrite=True) as out:
                while True:
                    chunk = await up.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
            saved += 1
        return {"ok": True, "saved": saved}
