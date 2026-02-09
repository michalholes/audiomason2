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


def _parse_root(root: str) -> RootName:
    try:
        return RootName(root)
    except Exception as e:
        raise HTTPException(status_code=400, detail="invalid root") from e


def _norm_rel_path(p: str) -> str:
    # Allow Unicode names. Only normalize obvious unsafe leading slashes.
    p = p.strip()
    if not p:
        return "."
    return p.lstrip("/")


def mount_fs(app: FastAPI) -> None:
    @app.get("/api/fs/list")
    def fs_list(request: Request, root: str, path: str = ".", recursive: int = 0) -> dict[str, Any]:
        fs = _get_file_service(request)
        r = _parse_root(root)
        entries = fs.list_dir(r, _norm_rel_path(path), recursive=bool(recursive))
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
        st = fs.stat(r, _norm_rel_path(path))
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
        return {"exists": fs.exists(r, _norm_rel_path(path))}

    @app.post("/api/fs/mkdir")
    def fs_mkdir(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        root = payload.get("root")
        path = payload.get("path")
        parents = bool(payload.get("parents", True))
        if not isinstance(root, str) or not isinstance(path, str):
            raise HTTPException(status_code=400, detail="root and path are required")
        fs = _get_file_service(request)
        fs.mkdir(_parse_root(root), _norm_rel_path(path), parents=parents, exist_ok=True)
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
        fs.rename(_parse_root(root), _norm_rel_path(src), _norm_rel_path(dst), overwrite=overwrite)
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
        fs.copy(_parse_root(root), _norm_rel_path(src), _norm_rel_path(dst), overwrite=overwrite)
        return {"ok": True}

    @app.post("/api/fs/delete_file")
    def fs_delete_file(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        root = payload.get("root")
        path = payload.get("path")
        if not isinstance(root, str) or not isinstance(path, str):
            raise HTTPException(status_code=400, detail="root and path are required")
        fs = _get_file_service(request)
        fs.delete_file(_parse_root(root), _norm_rel_path(path))
        return {"ok": True}

    @app.post("/api/fs/rmdir")
    def fs_rmdir(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        root = payload.get("root")
        path = payload.get("path")
        if not isinstance(root, str) or not isinstance(path, str):
            raise HTTPException(status_code=400, detail="root and path are required")
        fs = _get_file_service(request)
        fs.rmdir(_parse_root(root), _norm_rel_path(path))
        return {"ok": True}

    @app.post("/api/fs/rmtree")
    def fs_rmtree(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        root = payload.get("root")
        path = payload.get("path")
        if not isinstance(root, str) or not isinstance(path, str):
            raise HTTPException(status_code=400, detail="root and path are required")
        fs = _get_file_service(request)
        fs.rmtree(_parse_root(root), _norm_rel_path(path))
        return {"ok": True}

    @app.get("/api/fs/checksum")
    def fs_checksum(request: Request, root: str, path: str, algo: str = "sha256") -> dict[str, Any]:
        fs = _get_file_service(request)
        r = _parse_root(root)
        digest = fs.checksum(r, _norm_rel_path(path), algo=algo)
        return {"algo": algo, "digest": digest}

    @app.post("/api/fs/upload_file")
    async def fs_upload_file(
        request: Request,
        root: str = Form(...),  # noqa: B008
        path: str = Form(...),  # noqa: B008
        overwrite: int = Form(0),  # noqa: B008
        file: UploadFile = File(...),  # noqa: B008
    ) -> dict[str, Any]:
        fs = _get_file_service(request)
        r = _parse_root(root)
        rel = _norm_rel_path(path)
        if fs.exists(r, rel) and not bool(overwrite):
            raise HTTPException(status_code=409, detail="exists")
        with fs.open_write(r, rel, overwrite=bool(overwrite)) as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        return {"ok": True, "path": rel}

    @app.post("/api/fs/upload_dir")
    async def fs_upload_dir(
        request: Request,
        root: str = Form(...),  # noqa: B008
        base_path: str = Form("."),  # noqa: B008
        overwrite: int = Form(0),  # noqa: B008
        files: list[UploadFile] = File(...),  # noqa: B008
        relpaths: list[str] | None = Form(None),  # noqa: B008
    ) -> dict[str, Any]:
        fs = _get_file_service(request)
        r = _parse_root(root)
        base = _norm_rel_path(base_path)
        if relpaths is None:
            relpaths = [(f.filename or "upload.bin") for f in files]
        if len(relpaths) != len(files):
            raise HTTPException(status_code=400, detail="relpaths length mismatch")

        saved = 0
        for up, rel in zip(files, relpaths, strict=True):
            rel = _norm_rel_path(rel)
            target = rel if base in {".", ""} else f"{base.rstrip('/')}/{rel}"
            parent = target.rsplit("/", 1)[0] if "/" in target else ""
            if parent:
                fs.mkdir(r, parent, parents=True, exist_ok=True)
            if fs.exists(r, target) and not bool(overwrite):
                raise HTTPException(status_code=409, detail=f"exists: {target}")
            with fs.open_write(r, target, overwrite=bool(overwrite)) as out:
                while True:
                    chunk = await up.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
            saved += 1

        return {"ok": True, "saved": saved}

    @app.get("/api/fs/download_file")
    def fs_download_file(request: Request, root: str, path: str) -> StreamingResponse:
        fs = _get_file_service(request)
        r = _parse_root(root)
        rel = _norm_rel_path(path)

        def _iter() -> Any:
            with fs.open_read(r, rel) as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk

        filename = rel.split("/")[-1] or "download.bin"
        return StreamingResponse(
            _iter(),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/fs/download_dir_archive")
    def fs_download_dir_archive(
        request: Request, root: str, path: str, format: str = "zip"
    ) -> StreamingResponse:
        fs = _get_file_service(request)
        r = _parse_root(root)
        rel = _norm_rel_path(path)

        entries = fs.list_dir(r, rel, recursive=True)
        files = [e for e in entries if not e.is_dir]
        files.sort(key=lambda e: e.rel_path)

        if format not in {"zip", "tar"}:
            raise HTTPException(status_code=400, detail="format must be zip or tar")

        buf = io.BytesIO()
        if format == "zip":
            with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
                for e in files:
                    arcname = e.rel_path
                    with fs.open_read(r, e.rel_path) as f:
                        zf.writestr(arcname, f.read())
            media = "application/zip"
            out_name = (rel.rstrip("/").split("/")[-1] or "dir") + ".zip"
        else:
            with tarfile.open(fileobj=buf, mode="w") as tf:
                for e in files:
                    with fs.open_read(r, e.rel_path) as f:
                        data = f.read()
                    info = tarfile.TarInfo(name=e.rel_path)
                    info.size = len(data)
                    tf.addfile(info, io.BytesIO(data))
            media = "application/x-tar"
            out_name = (rel.rstrip("/").split("/")[-1] or "dir") + ".tar"

        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type=media,
            headers={"Content-Disposition": f'attachment; filename="{out_name}"'},
        )
