from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from audiomason.core.jobs.model import JobState, JobType
from audiomason.core.loader import PluginLoader
from audiomason.core.orchestration import Orchestrator

from ..util.fs import find_repo_root


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


def _serialize_job(job: Any) -> dict[str, Any]:
    # Job is audiomason.core.jobs.model.Job
    return job.to_dict()


def mount_jobs(app: FastAPI) -> None:
    orch = Orchestrator()

    @app.get("/api/jobs")
    def list_jobs() -> dict[str, Any]:
        jobs = [_serialize_job(j) for j in orch.list_jobs()]
        return {"items": jobs}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        try:
            job = orch.get_job(job_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        return {"item": _serialize_job(job)}

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict[str, Any]:
        try:
            orch.cancel(job_id)
            job = orch.get_job(job_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        return {"item": _serialize_job(job)}

    @app.get("/api/jobs/{job_id}/log")
    def read_job_log(job_id: str, offset: int = 0, limit_bytes: int = 64 * 1024) -> dict[str, Any]:
        try:
            text, next_offset = orch.read_log(job_id, offset=offset, limit_bytes=limit_bytes)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        return {"text": text, "next_offset": next_offset}

    @app.post("/api/jobs/process")
    def create_process_job(payload: dict[str, Any]) -> dict[str, Any]:
        pipeline_path = payload.get("pipeline_path")
        sources = payload.get("sources")
        if not isinstance(pipeline_path, str) or not pipeline_path:
            raise HTTPException(status_code=400, detail="pipeline_path is required")
        if not isinstance(sources, list) or not sources:
            raise HTTPException(status_code=400, detail="sources must be a non-empty list")
        srcs: list[str] = [str(x) for x in sources]

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

    @app.post("/api/jobs/wizard")
    def create_wizard_job(payload: dict[str, Any]) -> dict[str, Any]:
        wizard_id = payload.get("wizard_id")
        wizard_path = payload.get("wizard_path")
        wizard_payload = payload.get("payload", {})
        if not isinstance(wizard_id, str) or not wizard_id:
            raise HTTPException(status_code=400, detail="wizard_id is required")
        if not isinstance(wizard_path, str) or not wizard_path:
            raise HTTPException(status_code=400, detail="wizard_path is required")
        if not isinstance(wizard_payload, dict):
            raise HTTPException(status_code=400, detail="payload must be a dict")

        job = orch.jobs.create_job(
            JobType.WIZARD,
            meta={
                "wizard_id": wizard_id,
                "wizard_path": wizard_path,
                "payload_json": json.dumps(
                    wizard_payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
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
