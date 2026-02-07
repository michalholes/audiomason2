from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException

from audiomason.core.config_service import ConfigService
from audiomason.core.context import ProcessingContext
from audiomason.core.jobs.model import JobState, JobType
from audiomason.core.loader import PluginLoader
from audiomason.core.orchestration import Orchestrator
from audiomason.core.orchestration_models import ProcessRequest, WizardRequest
from audiomason.core.plugin_registry import PluginRegistry

from ..util.fs import find_repo_root


def _user_plugins_root() -> Path:
    return Path.home() / ".audiomason/plugins"


def _plugin_loader() -> PluginLoader:
    repo = find_repo_root()
    cfg = ConfigService()
    reg = PluginRegistry(cfg)
    return PluginLoader(
        builtin_plugins_dir=repo / "plugins", user_plugins_dir=_user_plugins_root(), registry=reg
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
    def run_job(job_id: str, bg: BackgroundTasks) -> dict[str, Any]:
        try:
            job = orch.get_job(job_id)
        except Exception as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

        if job.state != JobState.PENDING:
            raise HTTPException(status_code=400, detail="job is not pending")

        def _run() -> None:
            loader = _plugin_loader()

            if job.type == JobType.PROCESS:
                pipeline_path = job.meta.get("pipeline_path")
                sources_json = job.meta.get("sources_json", "[]")
                try:
                    sources = json.loads(sources_json)
                except Exception:
                    sources = []
                if not isinstance(pipeline_path, str) or not pipeline_path:
                    orch.jobs.append_log_line(job_id, "failed: missing pipeline_path")
                    j = orch.get_job(job_id)
                    j.transition(JobState.FAILED)
                    j.error = "missing pipeline_path"
                    orch.jobs.store.save_job(j)
                    return
                contexts: list[ProcessingContext] = []
                for i, s in enumerate(sources, 1):
                    contexts.append(ProcessingContext(id=f"ctx_{i}", source=Path(str(s))))
                req = ProcessRequest(
                    contexts=contexts, pipeline_path=Path(pipeline_path), plugin_loader=loader
                )
                j = orch.get_job(job_id)
                j.transition(JobState.RUNNING)
                j.started_at = datetime.now(UTC).isoformat()
                orch.jobs.store.save_job(j)
                orch.jobs.append_log_line(job_id, "started")
                asyncio.run(orch._run_process_job(job_id, req))
                return

            if job.type == JobType.WIZARD:
                wizard_id = job.meta.get("wizard_id", "")
                wizard_path = job.meta.get("wizard_path", "")
                payload_json = job.meta.get("payload_json", "{}")
                try:
                    data = json.loads(payload_json)
                except Exception:
                    data = {}
                if not isinstance(data, dict):
                    data = {}
                wizard_req = WizardRequest(
                    wizard_id=str(wizard_id),
                    wizard_path=Path(str(wizard_path)),
                    plugin_loader=loader,
                    payload=data,
                )
                j = orch.get_job(job_id)
                j.transition(JobState.RUNNING)
                j.started_at = datetime.now(UTC).isoformat()
                orch.jobs.store.save_job(j)
                orch.jobs.append_log_line(job_id, "started")
                asyncio.run(orch._run_wizard_job(job_id, wizard_req))
                return

            orch.jobs.append_log_line(job_id, f"failed: unsupported job type: {job.type}")
            j = orch.get_job(job_id)
            j.transition(JobState.FAILED)
            j.error = f"unsupported job type: {job.type}"
            orch.jobs.store.save_job(j)

        bg.add_task(_run)
        job = orch.get_job(job_id)
        return {"item": _serialize_job(job)}
