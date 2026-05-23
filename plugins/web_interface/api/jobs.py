from __future__ import annotations

import json
from typing import cast

from fastapi import FastAPI, HTTPException, Request

from audiomason.core.jobs.model import Job, JobType
from audiomason.core.orchestration import Orchestrator

from ..util.web_observability import web_operation


def _serialize_job(job: Job) -> dict[str, object]:
    return job.to_dict()


def mount_jobs(app: FastAPI) -> None:
    orch = Orchestrator()

    def list_jobs(request: Request) -> dict[str, object]:
        with web_operation(request, name="jobs.list", ctx={}):
            jobs = [_serialize_job(j) for j in orch.list_jobs()]
            return {"items": jobs}

    def get_job(request: Request, job_id: str) -> dict[str, object]:
        with web_operation(request, name="jobs.get", ctx={"job_id": job_id}):
            try:
                job = orch.get_job(job_id)
            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            return {"item": _serialize_job(job)}

    def cancel_job(request: Request, job_id: str) -> dict[str, object]:
        with web_operation(request, name="jobs.cancel", ctx={"job_id": job_id}):
            try:
                orch.cancel(job_id)
                job = orch.get_job(job_id)
            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e)) from e
            return {"item": _serialize_job(job)}

    def read_job_log(
        request: Request, job_id: str, offset: int = 0, limit_bytes: int = 64 * 1024
    ) -> dict[str, object]:
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

    def create_process_job(request: Request, payload: dict[str, object]) -> dict[str, object]:
        pipeline_path = payload.get("pipeline_path")
        sources = payload.get("sources")
        if not isinstance(pipeline_path, str) or not pipeline_path:
            raise HTTPException(status_code=400, detail="pipeline_path is required")
        if not isinstance(sources, list) or not sources:
            raise HTTPException(status_code=400, detail="sources must be a non-empty list")
        source_items = cast(list[object], sources)
        srcs: list[str] = [str(x) for x in source_items]

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

    app.add_api_route("/api/jobs", list_jobs, methods=["GET"])
    app.add_api_route("/api/jobs/{job_id}", get_job, methods=["GET"])
    app.add_api_route("/api/jobs/{job_id}/cancel", cancel_job, methods=["POST"])
    app.add_api_route("/api/jobs/{job_id}/log", read_job_log, methods=["GET"])
    app.add_api_route("/api/jobs/process", create_process_job, methods=["POST"])
