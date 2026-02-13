from __future__ import annotations

import io
import tarfile
import zipfile
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from audiomason.core.config import ConfigResolver
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

from ..util.web_observability import web_operation


def _get_resolver(request: Request) -> ConfigResolver:
    resolver = getattr(request.app.state, "config_resolver", None)
    if isinstance(resolver, ConfigResolver):
        return resolver
    return ConfigResolver()


def _get_file_service(request: Request) -> FileService:
    fs = getattr(request.app.state, "file_service", None)
    if isinstance(fs, FileService):
        return fs
    resolver = _get_resolver(request)
    fs = FileService.from_resolver(resolver)
    request.app.state.file_service = fs
    return fs


def _read_all(fs: FileService, root: RootName, rel_path: str) -> bytes:
    with fs.open_read(root, rel_path) as f:
        return f.read()


def _parse_root(root: str) -> RootName:
    try:
        return RootName(root)
    except Exception as e:
        raise HTTPException(status_code=400, detail="invalid root") from e


def _norm_rel_path(p: str) -> str:
    # Allow Unicode names. Only normalize obvious unsafe leading slash.
    p = p.strip()
    if not p:
        return "."
    p = p.lstrip("/")
    parts = [x for x in p.split("/") if x not in {"", "."}]
    if any(x == ".." for x in parts):
        raise HTTPException(status_code=400, detail="invalid path")
    return "/".join(parts) if parts else "."


def mount_fs(app: FastAPI) -> None:
    @app.get("/api/fs/list")
    def fs_list(request: Request, root: str, path: str = ".", recursive: int = 0) -> dict[str, Any]:
        fs = _get_file_service(request)
        r = _parse_root(root)
        rel = _norm_rel_path(path)
        with web_operation(
            request,
            name="fs.list",
            ctx={"root": r.value, "path": rel, "recursive": int(bool(recursive))},
        ):
            entries = fs.list_dir(r, rel, recursive=bool(recursive))
            items: list[dict[str, Any]] = []
            for e in entries:
                items.append(
                    {
                        "path": e.rel_path,
                        "is_dir": e.is_dir,
                        "size": e.size,
                        "mtime_ts": int(e.mtime) if e.mtime is not None else None,
                    }
                )
            return {"items": items}

    @app.get("/api/fs/stat")
    def fs_stat(request: Request, root: str, path: str) -> dict[str, Any]:
        fs = _get_file_service(request)
        r = _parse_root(root)
        rel = _norm_rel_path(path)
        with web_operation(request, name="fs.stat", ctx={"root": r.value, "path": rel}):
            st = fs.stat(r, rel)
            return {
                "item": {
                    "path": st.rel_path,
                    "is_dir": st.is_dir,
                    "size": st.size,
                    "mtime_ts": int(st.mtime),
                }
            }

    @app.get("/api/fs/exists")
    def fs_exists(request: Request, root: str, path: str) -> dict[str, Any]:
        fs = _get_file_service(request)
        r = _parse_root(root)
        rel = _norm_rel_path(path)
        with web_operation(request, name="fs.exists", ctx={"root": r.value, "path": rel}):
            return {"exists": fs.exists(r, rel)}

    @app.post("/api/fs/mkdir")
    def fs_mkdir(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        root = payload.get("root")
        path = payload.get("path")
        parents = bool(payload.get("parents", True))
        if not isinstance(root, str) or not isinstance(path, str):
            raise HTTPException(status_code=400, detail="root and path are required")
        fs = _get_file_service(request)
        r = _parse_root(root)
        rel = _norm_rel_path(path)
        with web_operation(
            request,
            name="fs.mkdir",
            ctx={"root": r.value, "path": rel, "parents": int(parents)},
        ):
            fs.mkdir(r, rel, parents=parents, exist_ok=True)
        return {"ok": True}

    @app.post("/api/fs/rename")
    def fs_rename(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        root = payload.get("root")
        src = payload.get("src")
        dst = payload.get("dst")
        overwrite = bool(payload.get("overwrite", False))
        if not isinstance(root, str) or not isinstance(src, str) or not isinstance(dst, str):
            raise HTTPException(status_code=400, detail="root, src, dst are required")
        fs = _get_file_service(request)
        r = _parse_root(root)
        src_rel = _norm_rel_path(src)
        dst_rel = _norm_rel_path(dst)
        with web_operation(
            request,
            name="fs.rename",
            ctx={"root": r.value, "src": src_rel, "dst": dst_rel, "overwrite": int(overwrite)},
        ):
            fs.rename(r, src_rel, dst_rel, overwrite=overwrite)
        return {"ok": True}

    @app.post("/api/fs/copy")
    def fs_copy(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        root = payload.get("root")
        src = payload.get("src")
        dst = payload.get("dst")
        overwrite = bool(payload.get("overwrite", False))
        if not isinstance(root, str) or not isinstance(src, str) or not isinstance(dst, str):
            raise HTTPException(status_code=400, detail="root, src, dst are required")
        fs = _get_file_service(request)
        r = _parse_root(root)
        src_rel = _norm_rel_path(src)
        dst_rel = _norm_rel_path(dst)
        with web_operation(
            request,
            name="fs.copy",
            ctx={"root": r.value, "src": src_rel, "dst": dst_rel, "overwrite": int(overwrite)},
        ):
            fs.copy(r, src_rel, dst_rel, overwrite=overwrite)
        return {"ok": True}

    @app.post("/api/fs/delete_file")
    def fs_delete_file(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        root = payload.get("root")
        path = payload.get("path")
        if not isinstance(root, str) or not isinstance(path, str):
            raise HTTPException(status_code=400, detail="root and path are required")
        fs = _get_file_service(request)
        r = _parse_root(root)
        rel = _norm_rel_path(path)
        with web_operation(request, name="fs.delete_file", ctx={"root": r.value, "path": rel}):
            fs.delete_file(r, rel)
        return {"ok": True}

    @app.post("/api/fs/rmdir")
    def fs_rmdir(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        root = payload.get("root")
        path = payload.get("path")
        if not isinstance(root, str) or not isinstance(path, str):
            raise HTTPException(status_code=400, detail="root and path are required")
        fs = _get_file_service(request)
        r = _parse_root(root)
        rel = _norm_rel_path(path)
        with web_operation(request, name="fs.rmdir", ctx={"root": r.value, "path": rel}):
            fs.rmdir(r, rel)
        return {"ok": True}

    @app.get("/api/fs/read_bytes")
    def fs_read_bytes(request: Request, root: str, path: str) -> StreamingResponse:
        fs = _get_file_service(request)
        r = _parse_root(root)
        rel = _norm_rel_path(path)
        with (
            web_operation(request, name="fs.read_bytes", ctx={"root": r.value, "path": rel}),
            fs.open_read(r, rel) as f,
        ):
            data = f.read()
        return StreamingResponse(io.BytesIO(data), media_type="application/octet-stream")

    @app.post("/api/fs/write_bytes")
    async def fs_write_bytes(
        request: Request,
        root: str = Form(...),
        path: str = Form(...),
        overwrite: int = Form(1),
        file: UploadFile = File(...),  # noqa: B008
    ) -> dict[str, Any]:
        if file is None:
            raise HTTPException(status_code=400, detail="file is required")
        fs = _get_file_service(request)
        r = _parse_root(root)
        rel = _norm_rel_path(path)
        data = await file.read()
        with (
            web_operation(
                request,
                name="fs.write_bytes",
                ctx={"root": r.value, "path": rel, "overwrite": int(bool(overwrite))},
            ),
            fs.open_write(r, rel, overwrite=bool(overwrite)) as f,
        ):
            f.write(data)
        return {"ok": True}

    @app.get("/api/fs/archive")
    def fs_archive(
        request: Request, root: str, path: str = ".", fmt: str = "zip"
    ) -> StreamingResponse:
        fs = _get_file_service(request)
        r = _parse_root(root)
        rel = _norm_rel_path(path)
        fmt = (fmt or "zip").lower().strip()
        if fmt not in {"zip", "tar"}:
            raise HTTPException(status_code=400, detail="invalid fmt")

        with web_operation(
            request,
            name="fs.archive",
            ctx={"root": r.value, "path": rel, "fmt": fmt},
        ):
            entries = fs.list_dir(r, rel, recursive=True)
            buf = io.BytesIO()
            if fmt == "zip":
                with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for e in entries:
                        if e.is_dir:
                            continue
                        zf.writestr(e.rel_path, (_read_all(fs, r, e.rel_path)))
                buf.seek(0)
                return StreamingResponse(buf, media_type="application/zip")
            # tar
            with tarfile.open(fileobj=buf, mode="w") as tf:
                for e in entries:
                    if e.is_dir:
                        continue
                    data = _read_all(fs, r, e.rel_path)
                    ti = tarfile.TarInfo(name=e.rel_path)
                    ti.size = len(data)
                    tf.addfile(ti, io.BytesIO(data))
            buf.seek(0)
            return StreamingResponse(buf, media_type="application/x-tar")
