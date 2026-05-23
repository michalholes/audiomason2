from __future__ import annotations

from typing import Annotated, Protocol, cast

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile

from audiomason.core.config import ConfigResolver
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

from ..util.web_observability import web_operation


class _StateView(Protocol):
    config_resolver: object
    file_service: object
    verbosity: object


def _resolver(request: Request) -> ConfigResolver:
    state = cast(_StateView, request.state)
    try:
        r = state.config_resolver
    except Exception:
        r = None
    if isinstance(r, ConfigResolver):
        return r
    return ConfigResolver()


def _fs(request: Request) -> FileService:
    state = cast(_StateView, request.state)
    try:
        fs = state.file_service
    except Exception:
        fs = None
    if isinstance(fs, FileService):
        return fs
    fs = FileService.from_resolver(_resolver(request))
    state.file_service = fs
    return fs


def _debug(request: Request) -> bool:
    state = cast(_StateView, request.state)
    try:
        v = state.verbosity
    except Exception:
        v = 1
    if isinstance(v, int):
        return v >= 3
    if isinstance(v, str):
        try:
            return int(v) >= 3
        except ValueError:
            return False
    return False


def mount_stage(app: FastAPI) -> None:
    # Backward-compatible stage endpoints implemented via FileService.

    def list_stage(request: Request) -> dict[str, object]:
        fs = _fs(request)
        items: list[dict[str, object]] = []
        with web_operation(
            request, name="stage.list", ctx={"root": RootName.STAGE.value, "path": "."}
        ):
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
        out: dict[str, object] = {"items": items, "dir": str(fs.root_dir(RootName.STAGE))}
        if _debug(request):
            out["root"] = RootName.STAGE.value
        return out

    def delete_stage(request: Request, name: str) -> dict[str, object]:
        fs = _fs(request)
        rel = name.lstrip("/")
        try:
            with web_operation(
                request,
                name="stage.delete",
                ctx={"root": RootName.STAGE.value, "path": rel},
            ):
                fs.delete_file(RootName.STAGE, rel)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail="not found") from e
        return {"ok": True}

    async def upload_stage(
        request: Request,
        files: Annotated[list[UploadFile], File()],
        relpaths: Annotated[list[str] | None, Form()] = None,
    ) -> dict[str, object]:
        fs = _fs(request)
        if relpaths is None:
            relpaths = [f.filename or "upload.bin" for f in files]
        if len(relpaths) != len(files):
            raise HTTPException(status_code=400, detail="relpaths length mismatch")

        saved = 0
        with web_operation(
            request,
            name="stage.upload",
            ctx={"root": RootName.STAGE.value, "count": len(files)},
        ):
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

        return {"saved": saved}

    app.add_api_route("/api/stage", list_stage, methods=["GET"])
    app.add_api_route("/api/stage/{name:path}", delete_stage, methods=["DELETE"])
    app.add_api_route("/api/stage/upload", upload_stage, methods=["POST"])
