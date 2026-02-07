"""Core orchestration layer (Phase 2).

The orchestration layer:
- creates jobs
- runs pipeline execution behind a stable API
- enforces the phase contract centrally

This module is UI-agnostic: CLI and the future web interface can both call it.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from audiomason.core.jobs.api import JobService
from audiomason.core.jobs.model import Job, JobState, JobType
from audiomason.core.orchestration_models import ProcessRequest, WizardRequest
from audiomason.core.phase import PhaseGuard
from audiomason.core.pipeline import PipelineExecutor


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


class Orchestrator:
    """Orchestration facade for Phase 2+."""

    def __init__(self, job_service: JobService | None = None) -> None:
        self._jobs = job_service if job_service is not None else JobService()

    @property
    def jobs(self) -> JobService:
        return self._jobs

    def start_process(self, request: ProcessRequest) -> str:
        """Create and start a processing job.

        The job is started in the background when a running asyncio loop exists.
        """
        job = self._jobs.create_job(
            JobType.PROCESS,
            meta={
                "pipeline": str(request.pipeline_path),
            },
        )

        # Mark running
        job.transition(JobState.RUNNING)
        job.started_at = _utcnow_iso()
        self._jobs.store.save_job(job)

        self._jobs.append_log_line(job.job_id, "started")

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No loop; run synchronously.
            asyncio.run(self._run_process_job(job.job_id, request))
        else:
            loop.create_task(self._run_process_job(job.job_id, request))

        return job.job_id

    def start_wizard(self, request: WizardRequest) -> str:
        job = self._jobs.create_job(JobType.WIZARD, meta={"wizard_id": request.wizard_id})
        job.transition(JobState.RUNNING)
        job.started_at = _utcnow_iso()
        self._jobs.store.save_job(job)

        self._jobs.append_log_line(job.job_id, "wizard execution not implemented in phase 2")

        job.transition(JobState.FAILED)
        job.error = "wizard execution not implemented in phase 2"
        job.finished_at = _utcnow_iso()
        self._jobs.store.save_job(job)
        return job.job_id

    def cancel(self, job_id: str) -> None:
        self._jobs.cancel_job(job_id)

    def get_job(self, job_id: str) -> Job:
        return self._jobs.get_job(job_id)

    def list_jobs(self) -> list[Job]:
        return self._jobs.list_jobs()

    def read_log(
        self, job_id: str, offset: int = 0, limit_bytes: int = 64 * 1024
    ) -> tuple[str, int]:
        return self._jobs.read_log(job_id, offset=offset, limit_bytes=limit_bytes)

    async def _run_process_job(self, job_id: str, request: ProcessRequest) -> None:
        with PhaseGuard.processing():
            try:
                await self._run_process_job_impl(job_id, request)
            except Exception as e:
                job = self._jobs.get_job(job_id)
                job.transition(JobState.FAILED)
                job.error = str(e)
                job.finished_at = _utcnow_iso()
                self._jobs.store.save_job(job)
                self._jobs.append_log_line(job_id, f"failed: {e}")

    async def _run_process_job_impl(self, job_id: str, request: ProcessRequest) -> None:
        contexts = request.contexts
        total = max(1, len(contexts))
        executor = PipelineExecutor(request.plugin_loader)

        for i, ctx in enumerate(contexts, 1):
            job = self._jobs.get_job(job_id)
            if job.cancel_requested:
                job.transition(JobState.CANCELLED)
                job.finished_at = _utcnow_iso()
                self._jobs.store.save_job(job)
                self._jobs.append_log_line(job_id, "cancelled")
                return

            self._jobs.append_log_line(job_id, f"processing: {ctx.source}")
            await executor.execute_from_yaml(request.pipeline_path, ctx)

            job = self._jobs.get_job(job_id)
            job.progress = float(i) / float(total)
            self._jobs.store.save_job(job)

        job = self._jobs.get_job(job_id)
        job.progress = 1.0
        job.transition(JobState.SUCCEEDED)
        job.finished_at = _utcnow_iso()
        self._jobs.store.save_job(job)
        self._jobs.append_log_line(job_id, "succeeded")
