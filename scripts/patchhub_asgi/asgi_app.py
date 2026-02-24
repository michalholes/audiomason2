from __future__ import annotations

import asyncio
import json
import mimetypes
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)

from patchhub.app_support import read_tail

from .async_app_core import AsyncAppCore
from .async_offload import to_thread
from .sse_jsonl_stream import stream_job_events_sse

UPLOAD_PATCH_FILE: Any = File(...)


def _json_bytes_response(status: int, data: bytes) -> Response:
    return Response(content=data, status_code=status, media_type="application/json")


def _guess_content_type(path: Path) -> str:
    ctype, _ = mimetypes.guess_type(path.name)
    return ctype or "application/octet-stream"


def create_app(*, repo_root: Path, cfg: Any) -> FastAPI:
    app = FastAPI()
    core = AsyncAppCore(repo_root=repo_root, cfg=cfg)
    app.state.core = core

    @app.on_event("startup")
    async def _startup() -> None:
        await core.startup()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await core.shutdown()

    @app.get("/")
    async def index() -> HTMLResponse:
        html = core.render_index().encode("utf-8")
        return HTMLResponse(content=html, status_code=200)

    @app.get("/debug")
    async def debug() -> HTMLResponse:
        html = core.render_debug().encode("utf-8")
        return HTMLResponse(content=html, status_code=200)

    @app.get("/static/{rel_path:path}")
    async def static(rel_path: str) -> FileResponse:
        base = Path(__file__).resolve().parent.parent / "patchhub" / "static"
        p = (base / rel_path).resolve()
        if base not in p.parents:
            raise HTTPException(status_code=404, detail="Not found")
        if not p.exists() or not p.is_file():
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(p, media_type=_guess_content_type(p))

    @app.get("/api/config")
    async def api_config() -> Response:
        status, data = core.api_config()
        return _json_bytes_response(status, data)

    @app.get("/api/fs/list")
    async def api_fs_list(path: str = "") -> Response:
        status, data = core.api_fs_list(path)
        return _json_bytes_response(status, data)

    @app.get("/api/patches/latest")
    async def api_patches_latest() -> Response:
        status, data = core.api_patches_latest()
        return _json_bytes_response(status, data)

    @app.get("/api/fs/read_text")
    async def api_fs_read_text(request: Request) -> Response:
        qs = dict(request.query_params)
        status, data = core.api_fs_read_text(qs)
        return _json_bytes_response(status, data)

    @app.get("/api/fs/download")
    async def api_fs_download(path: str = "") -> FileResponse:
        try:
            p = core.jail.resolve_rel(path)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if not p.exists() or not p.is_file():
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(p, media_type=_guess_content_type(p), filename=p.name)

    @app.get("/api/runs")
    async def api_runs(request: Request) -> Response:
        qs = dict(request.query_params)
        status, data = core.api_runs(qs)
        return _json_bytes_response(status, data)

    @app.get("/api/runner/tail")
    async def api_runner_tail(request: Request) -> Response:
        qs = dict(request.query_params)
        status, data = core.api_runner_tail(qs)
        return _json_bytes_response(status, data)

    @app.get("/api/jobs")
    async def api_jobs_list() -> JSONResponse:
        mem = await core.queue.list_jobs()
        mem_by_id = {j.job_id: j for j in mem}

        from patchhub.job_store import list_job_jsons

        disk_raw = list_job_jsons(core.jobs_root, limit=200)
        disk = []
        for r in disk_raw:
            jid = str(r.get("job_id", ""))
            if not jid or jid in mem_by_id:
                continue
            j = core._load_job_from_disk(jid)
            if j is not None:
                disk.append(j)

        jobs = mem + disk
        jobs.sort(key=lambda j: str(j.created_utc or ""), reverse=True)
        return JSONResponse({"ok": True, "jobs": [j.to_json() for j in jobs]})

    @app.get("/api/jobs/{job_id}")
    async def api_jobs_get(job_id: str) -> JSONResponse:
        job = await core.queue.get_job(job_id)
        if job is None:
            job = core._load_job_from_disk(job_id)
        if job is None:
            return JSONResponse({"ok": False, "error": "Not found"}, status_code=404)
        return JSONResponse({"ok": True, "job": job.to_json()})

    @app.get("/api/jobs/{job_id}/log_tail")
    async def api_jobs_log_tail(job_id: str, lines: int = 200) -> JSONResponse:
        job = await core.queue.get_job(job_id)
        if job is None:
            job = core._load_job_from_disk(job_id)
        if job is None:
            return JSONResponse({"ok": False, "error": "Not found"}, status_code=404)
        log_path = core.jobs_root / str(job_id) / "runner.log"
        return JSONResponse({"ok": True, "job_id": job_id, "tail": read_tail(log_path, lines)})

    @app.post("/api/jobs/{job_id}/cancel")
    async def api_jobs_cancel(job_id: str) -> Response:
        ok = await core.queue.cancel(job_id)
        if not ok:
            return JSONResponse({"ok": False, "error": "Cannot cancel"}, status_code=409)
        return JSONResponse({"ok": True, "job_id": job_id})

    @app.post("/api/jobs/enqueue")
    async def api_jobs_enqueue(body: dict[str, Any]) -> Response:
        from patchhub.app_api_jobs import api_jobs_enqueue

        # Reuse legacy parsing/validation logic, but enqueue via async queue.
        # The legacy helper calls self.queue.enqueue(job), which is sync.
        # We provide a small adapter object with an async enqueue.

        class _Adapter:
            def __init__(self, core: AsyncAppCore) -> None:
                self.core = core
                self.cfg = core.cfg
                self.jail = core.jail
                self.patches_root = core.patches_root
                self.jobs_root = core.jobs_root
                self.queue = self

            def _load_job_from_disk(self, job_id: str):
                return core._load_job_from_disk(job_id)

            async def _enqueue_async(self, job: Any) -> None:
                await core.queue.enqueue(job)

            def enqueue(self, job: Any) -> None:
                asyncio.get_running_loop().create_task(self._enqueue_async(job))

        adapter = _Adapter(core)
        status, data = api_jobs_enqueue(adapter, body)
        return _json_bytes_response(status, data)

    @app.post("/api/parse_command")
    async def api_parse_command(body: dict[str, Any]) -> Response:
        status, data = core.api_parse_command(body)
        return _json_bytes_response(status, data)

    @app.post("/api/upload/patch")
    async def api_upload_patch(file: UploadFile = UPLOAD_PATCH_FILE) -> Response:
        filename = os.path.basename(file.filename or "")
        data = await file.read()
        status, resp = core.api_upload_patch(filename, data)
        return _json_bytes_response(status, resp)

    @app.post("/api/fs/mkdir")
    async def api_fs_mkdir(body: dict[str, Any]) -> Response:
        status, data = core.api_fs_mkdir(body)
        return _json_bytes_response(status, data)

    @app.post("/api/fs/rename")
    async def api_fs_rename(body: dict[str, Any]) -> Response:
        status, data = core.api_fs_rename(body)
        return _json_bytes_response(status, data)

    @app.post("/api/fs/delete")
    async def api_fs_delete(body: dict[str, Any]) -> Response:
        status, data = core.api_fs_delete(body)
        return _json_bytes_response(status, data)

    @app.post("/api/fs/unzip")
    async def api_fs_unzip(body: dict[str, Any]) -> Response:
        status, data = core.api_fs_unzip(body)
        return _json_bytes_response(status, data)

    @app.post("/api/fs/archive")
    async def api_fs_archive(body: dict[str, Any]) -> Response:
        paths = body.get("paths")
        if not isinstance(paths, list) or not paths:
            return JSONResponse(
                {"ok": False, "error": "paths must be a non-empty list"}, status_code=400
            )

        rel_paths: list[str] = []
        for x in paths:
            if not isinstance(x, str):
                continue
            rel = x.strip().lstrip("/")
            if rel:
                rel_paths.append(rel)
        if not rel_paths:
            return JSONResponse({"ok": False, "error": "No valid paths"}, status_code=400)
        rel_paths = sorted(set(rel_paths))

        def _build_archive_bytes_sync(core: AsyncAppCore, rel_paths: list[str]) -> bytes:
            files: list[tuple[str, Path]] = []
            seen: set[str] = set()
            for rel in rel_paths:
                p = core.jail.resolve_rel(rel)
                if not p.exists():
                    raise FileNotFoundError(rel)
                if p.is_file():
                    if rel not in seen:
                        files.append((rel, p))
                        seen.add(rel)
                    continue

                root = p
                for dirpath, dirnames, filenames in os.walk(root):
                    dirnames.sort()
                    filenames.sort()
                    dp = Path(dirpath)
                    for fn in filenames:
                        fp = dp / fn
                        if not fp.is_file():
                            continue
                        sub_rel = str(fp.relative_to(core.jail.patches_root())).replace(os.sep, "/")
                        if sub_rel not in seen:
                            files.append((sub_rel, fp))
                            seen.add(sub_rel)

            files.sort(key=lambda t: t[0])

            import io
            import zipfile

            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
                for arc, fp in files:
                    z.write(fp, arcname=arc.replace(os.sep, "/"))

            return buf.getvalue()

        try:
            data = await to_thread(_build_archive_bytes_sync, core, rel_paths)
        except FileNotFoundError as e:
            return JSONResponse({"ok": False, "error": f"Not found: {e.args[0]}"}, status_code=400)
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
        headers = {"Content-Disposition": 'attachment; filename="selection.zip"'}
        return Response(content=data, media_type="application/zip", headers=headers)

    @app.get("/api/debug/diagnostics")
    async def api_debug_diagnostics() -> JSONResponse:
        return JSONResponse(await core.diagnostics(), status_code=200)

    @app.get("/api/jobs/{job_id}/events")
    async def api_jobs_events(job_id: str) -> StreamingResponse:
        async def gen() -> AsyncIterator[bytes]:
            job = await core.queue.get_job(job_id)
            disk_job = None
            if job is None:
                disk_job = core._load_job_from_disk(job_id)

            if job is None and disk_job is None:
                data = json.dumps({"reason": "job_not_found"}, ensure_ascii=True)
                yield f"event: end\ndata: {data}\n\n".encode()
                return

            if disk_job is not None and job is None:
                jsonl_path = core._job_jsonl_path_from_fields(
                    job_id=str(job_id),
                    mode=str(disk_job.mode),
                    issue_id=str(disk_job.issue_id),
                )
            else:
                assert job is not None
                jsonl_path = core._job_jsonl_path(job)

            async def job_status() -> str | None:
                j = await core.queue.get_job(job_id)
                if j is not None:
                    return str(j.status)
                if disk_job is not None:
                    return str(disk_job.status)
                return None

            async for chunk in stream_job_events_sse(
                job_id=str(job_id),
                jsonl_path=jsonl_path,
                job_status=job_status,
            ):
                yield chunk

        return StreamingResponse(gen(), media_type="text/event-stream")

    return app
