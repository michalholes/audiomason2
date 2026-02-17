from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from audiomason.core.jobs.model import JobState, JobType
from audiomason.core.loader import PluginLoader
from audiomason.core.orchestration import Orchestrator
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

from ..util.fs import find_repo_root
from ..util.web_observability import web_operation


def _user_plugins_root() -> Path:
    return Path.home() / ".audiomason/plugins"


def _plugin_loader(request: Any | None = None) -> PluginLoader:
    injected = None
    if request is not None:
        injected = getattr(getattr(request, "app", None), "state", None)
        injected = getattr(injected, "plugin_loader", None)
    if isinstance(injected, PluginLoader):
        return injected

    repo = find_repo_root()
    return PluginLoader(
        builtin_plugins_dir=repo / "plugins", user_plugins_dir=_user_plugins_root(), registry=None
    )


def _get_resolver(request: Request) -> Any:
    resolver = getattr(request.app.state, "config_resolver", None)
    return resolver


def _get_file_service(request: Request) -> FileService:
    fs = getattr(request.app.state, "file_service", None)
    if isinstance(fs, FileService):
        return fs
    resolver = _get_resolver(request)
    from audiomason.core.config import ConfigResolver

    cr = resolver if isinstance(resolver, ConfigResolver) else ConfigResolver()
    fs = FileService.from_resolver(cr)
    request.app.state.file_service = fs
    return fs


def _parse_root_name(root: str) -> RootName:
    try:
        return RootName(root)
    except Exception as e:
        raise HTTPException(status_code=400, detail="invalid root") from e


def _norm_rel_path(p: str) -> str:
    p = p.strip()
    if not p:
        return "."
    p = p.lstrip("/")
    parts = [x for x in p.split("/") if x not in {"", "."}]
    if any(x == ".." for x in parts):
        raise HTTPException(status_code=400, detail="invalid path")
    return "/".join(parts) if parts else "."


def _serialize_job(job: Any) -> dict[str, Any]:
    # Job is audiomason.core.jobs.model.Job
    return job.to_dict()


def mount_jobs(app: FastAPI) -> None:
    orch = Orchestrator()

    @app.get("/api/jobs")
    def list_jobs(request: Request) -> dict[str, Any]:
        with web_operation(request, name="jobs.list", ctx={}):
            jobs = [_serialize_job(j) for j in orch.list_jobs()]
            return {"items": jobs}

    @app.get("/api/jobs/{job_id}")
    def get_job(request: Request, job_id: str) -> dict[str, Any]:
        with web_operation(request, name="jobs.get", ctx={"job_id": job_id}):
            try:
                job = orch.get_job(job_id)
            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            return {"item": _serialize_job(job)}

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(request: Request, job_id: str) -> dict[str, Any]:
        with web_operation(request, name="jobs.cancel", ctx={"job_id": job_id}):
            try:
                orch.cancel(job_id)
                job = orch.get_job(job_id)
            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            return {"item": _serialize_job(job)}

    @app.get("/api/jobs/{job_id}/log")
    def read_job_log(
        request: Request, job_id: str, offset: int = 0, limit_bytes: int = 64 * 1024
    ) -> dict[str, Any]:
        with web_operation(
            request,
            name="jobs.log",
            ctx={"job_id": job_id, "offset": int(offset), "limit_bytes": int(limit_bytes)},
        ):
            try:
                text, next_offset = orch.read_log(job_id, offset=offset, limit_bytes=limit_bytes)
            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            return {"text": text, "next_offset": next_offset}

    @app.post("/api/jobs/process")
    def create_process_job(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
        pipeline_path = payload.get("pipeline_path")
        sources = payload.get("sources")
        if not isinstance(pipeline_path, str) or not pipeline_path:
            raise HTTPException(status_code=400, detail="pipeline_path is required")
        if not isinstance(sources, list) or not sources:
            raise HTTPException(status_code=400, detail="sources must be a non-empty list")
        srcs: list[str] = [str(x) for x in sources]

        with web_operation(
            request,
            name="jobs.create_process",
            ctx={"pipeline_path": pipeline_path, "sources_count": len(srcs)},
        ):
            job = orch.jobs.create_job(
                JobType.PROCESS,
                meta={
                    "pipeline_path": pipeline_path,
                    "sources_json": json.dumps(
                        srcs, ensure_ascii=True, separators=(",", ":"), sort_keys=True
                    ),
                },
            )
        return {"job_id": job.job_id, "item": _serialize_job(job)}

    @app.post("/api/jobs/{job_id}/run")
    def run_job(request: Request, job_id: str, bg: BackgroundTasks) -> dict[str, Any]:
        try:
            job = orch.get_job(job_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

        if job.state != JobState.PENDING:
            raise HTTPException(status_code=400, detail="job is not pending")

        def _run() -> None:
            loader = _plugin_loader(request)

            try:
                orch.run_job(
                    job_id,
                    plugin_loader=loader,
                    verbosity=int(getattr(request.app.state, "verbosity", 1)),
                )
            except Exception as e:
                orch.jobs.append_log_line(job_id, f"failed: {e}")
                j = orch.get_job(job_id)
                j.transition(JobState.FAILED)
                j.error = str(e)
                orch.jobs.store.save_job(j)

        bg.add_task(_run)
        job = orch.get_job(job_id)
        return {"item": _serialize_job(job)}
