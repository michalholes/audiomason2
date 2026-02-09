"""Core orchestration layer (Phase 2).

The orchestration layer:
- creates jobs
- runs pipeline execution behind a stable API
- enforces the phase contract centrally

This module is UI-agnostic: CLI and the future web interface can both call it.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from audiomason.checkpoint import CheckpointManager
from audiomason.core.config import ConfigResolver
from audiomason.core.context import ProcessingContext
from audiomason.core.jobs.api import JobService
from audiomason.core.jobs.model import Job, JobState, JobType
from audiomason.core.logging import (
    VerbosityLevel,
    get_log_sink,
    get_logger,
    set_log_sink,
    set_verbosity,
)
from audiomason.core.orchestration_models import ProcessRequest, WizardRequest
from audiomason.core.phase import PhaseContractError, PhaseGuard
from audiomason.core.pipeline import PipelineExecutor
from audiomason.wizard_engine import WizardEngine


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


_LOGGER = get_logger(__name__)


def _parse_verbosity(value: object) -> VerbosityLevel:
    if isinstance(value, VerbosityLevel):
        return value
    if isinstance(value, int):
        try:
            return VerbosityLevel(value)
        except Exception:
            return VerbosityLevel.NORMAL
    if isinstance(value, str):
        v = value.strip().lower()
        mapping = {
            "0": VerbosityLevel.QUIET,
            "1": VerbosityLevel.NORMAL,
            "2": VerbosityLevel.VERBOSE,
            "3": VerbosityLevel.DEBUG,
            "quiet": VerbosityLevel.QUIET,
            "normal": VerbosityLevel.NORMAL,
            "verbose": VerbosityLevel.VERBOSE,
            "debug": VerbosityLevel.DEBUG,
        }
        return mapping.get(v, VerbosityLevel.NORMAL)
    return VerbosityLevel.NORMAL


def _resolve_effective_verbosity() -> VerbosityLevel:
    resolver = ConfigResolver()
    try:
        value, _source = resolver.resolve("logging.level")
    except Exception:
        value = "normal"
    return _parse_verbosity(value)


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
                "pipeline_path": str(request.pipeline_path),
                "sources_json": json.dumps(
                    [str(ctx.source) for ctx in request.contexts],
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            },
        )

        # Mark running
        job.transition(JobState.RUNNING)
        job.started_at = _utcnow_iso()
        self._jobs.store.save_job(job)

        prev_sink = get_log_sink()
        set_log_sink(lambda line: self._jobs.append_log_line(job.job_id, line))
        try:
            _LOGGER.info("started")
        finally:
            set_log_sink(prev_sink)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No loop; run synchronously.
            asyncio.run(self._run_process_job(job.job_id, request))
        else:
            loop.create_task(self._run_process_job(job.job_id, request))

        return job.job_id

    def start_wizard(self, request: WizardRequest) -> str:
        job = self._jobs.create_job(
            JobType.WIZARD,
            meta={
                "wizard_id": request.wizard_id,
                "wizard_path": str(request.wizard_path),
                "payload_json": json.dumps(
                    request.payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
                ),
            },
        )

        job.transition(JobState.RUNNING)
        job.started_at = _utcnow_iso()
        self._jobs.store.save_job(job)

        prev_sink = get_log_sink()
        set_log_sink(lambda line: self._jobs.append_log_line(job.job_id, line))
        try:
            _LOGGER.info("started")
        finally:
            set_log_sink(prev_sink)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self._run_wizard_job(job.job_id, request))
        else:
            loop.create_task(self._run_wizard_job(job.job_id, request))

        return job.job_id

    def run_job(self, job_id: str, *, plugin_loader: Any, verbosity: int = 1) -> None:
        """Run an existing PENDING job.

        UI layers may create jobs first (PENDING) and then request execution.
        This method owns the job state transitions and request construction.

        Args:
            job_id: Existing job id in PENDING state.
            plugin_loader: Plugin loader instance.
            verbosity: Verbosity override (see docs/specification.md).
        """
        job = self._jobs.get_job(job_id)
        if job.state != JobState.PENDING:
            raise RuntimeError("job is not pending")

        if job.type == JobType.PROCESS:
            pipeline_path = job.meta.get("pipeline_path")
            sources_json = job.meta.get("sources_json", "[]")
            if not isinstance(pipeline_path, str) or not pipeline_path:
                raise RuntimeError("missing pipeline_path")
            try:
                sources = json.loads(sources_json)
            except Exception:
                sources = []
            if not isinstance(sources, list):
                sources = []

            contexts: list[ProcessingContext] = []
            for i, s in enumerate(sources, 1):
                contexts.append(ProcessingContext(id=f"ctx_{i}", source=Path(str(s))))

            process_request = ProcessRequest(
                contexts=contexts,
                pipeline_path=Path(pipeline_path),
                plugin_loader=plugin_loader,
            )

            job.transition(JobState.RUNNING)
            job.started_at = _utcnow_iso()
            job.meta["verbosity_override"] = str(int(verbosity))
            self._jobs.store.save_job(job)

            prev_sink = get_log_sink()
            set_log_sink(lambda line: self._jobs.append_log_line(job.job_id, line))
            try:
                _LOGGER.info("started")
            finally:
                set_log_sink(prev_sink)

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(self._run_process_job(job.job_id, process_request))
            else:
                loop.create_task(self._run_process_job(job.job_id, process_request))
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

            wizard_request = WizardRequest(
                wizard_id=str(wizard_id),
                wizard_path=Path(str(wizard_path)),
                plugin_loader=plugin_loader,
                payload=data,
                verbosity=verbosity,
            )

            job.transition(JobState.RUNNING)
            job.started_at = _utcnow_iso()
            job.meta["verbosity_override"] = str(int(verbosity))
            self._jobs.store.save_job(job)

            prev_sink = get_log_sink()
            set_log_sink(lambda line: self._jobs.append_log_line(job.job_id, line))
            try:
                _LOGGER.info("started")
            finally:
                set_log_sink(prev_sink)

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(self._run_wizard_job(job.job_id, wizard_request))
            else:
                loop.create_task(self._run_wizard_job(job.job_id, wizard_request))
            return

        raise RuntimeError(f"unsupported job type: {job.type}")

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
        prev_sink = get_log_sink()
        set_log_sink(lambda line: self._jobs.append_log_line(job_id, line))
        set_verbosity(_resolve_effective_verbosity())
        try:
            job = self._jobs.get_job(job_id)
            override = job.meta.get("verbosity_override")
            if isinstance(override, str) and override.isdigit():
                set_verbosity(_parse_verbosity(int(override)))

            with PhaseGuard.processing():
                try:
                    await self._run_process_job_impl(job_id, request)
                except PhaseContractError as e:
                    job = self._jobs.get_job(job_id)
                    job.transition(JobState.FAILED)
                    job.error = str(e)
                    job.finished_at = _utcnow_iso()
                    self._jobs.store.save_job(job)
                    _LOGGER.error(f"failed: {e}")
                except Exception as e:
                    job = self._jobs.get_job(job_id)
                    job.transition(JobState.FAILED)
                    job.error = str(e)
                    job.finished_at = _utcnow_iso()
                    self._jobs.store.save_job(job)
                    _LOGGER.error(f"failed: {e}")
        finally:
            set_log_sink(prev_sink)

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
                _LOGGER.warning("cancelled")
                return

            _LOGGER.info(f"processing: {ctx.source}")
            await executor.execute_from_yaml(request.pipeline_path, ctx)

            job = self._jobs.get_job(job_id)
            job.progress = float(i) / float(total)
            self._jobs.store.save_job(job)

        job = self._jobs.get_job(job_id)
        job.progress = 1.0
        job.transition(JobState.SUCCEEDED)
        job.finished_at = _utcnow_iso()
        self._jobs.store.save_job(job)
        _LOGGER.info("succeeded")

    async def _run_wizard_job(self, job_id: str, request: WizardRequest) -> None:
        prev_sink = get_log_sink()
        set_log_sink(lambda line: self._jobs.append_log_line(job_id, line))
        set_verbosity(_resolve_effective_verbosity())
        try:
            job = self._jobs.get_job(job_id)
            override = job.meta.get("verbosity_override")
            if isinstance(override, str) and override.isdigit():
                set_verbosity(_parse_verbosity(int(override)))

            with PhaseGuard.processing():
                try:
                    await self._run_wizard_job_impl(job_id, request)
                except PhaseContractError as e:
                    ck = CheckpointManager()
                    try:
                        p = ck.save_job_failure_checkpoint(
                            job_id,
                            kind="wizard",
                            error=str(e),
                            meta=self._jobs.get_job(job_id).meta,
                        )
                        _LOGGER.info(f"checkpoint saved: {p}")
                    except Exception as ck_e:
                        _LOGGER.warning(f"checkpoint save failed: {ck_e}")

                    job = self._jobs.get_job(job_id)
                    job.transition(JobState.FAILED)
                    job.error = str(e)
                    job.finished_at = _utcnow_iso()
                    self._jobs.store.save_job(job)
                    _LOGGER.error(f"failed: {e}")
                except Exception as e:
                    job = self._jobs.get_job(job_id)
                    job.transition(JobState.FAILED)
                    job.error = str(e)
                    job.finished_at = _utcnow_iso()
                    self._jobs.store.save_job(job)
                    _LOGGER.error(f"failed: {e}")
        finally:
            set_log_sink(prev_sink)

    async def _run_wizard_job_impl(self, job_id: str, request: WizardRequest) -> None:
        _LOGGER.info(f"wizard: {request.wizard_id}")

        def _payload_input(prompt: str, options: dict[str, Any]) -> str:
            step_id = options.get("step_id")
            if isinstance(step_id, str) and step_id in request.payload:
                value = request.payload[step_id]
                return "" if value is None else str(value)

            key = options.get("key")
            if isinstance(key, str) and key in request.payload:
                value = request.payload[key]
                return "" if value is None else str(value)

            raise RuntimeError(f"missing wizard input for step: {step_id or key}")

        from audiomason.core.wizard_service import WizardService

        engine = WizardEngine(loader=request.plugin_loader, verbosity=request.verbosity)
        engine.set_input_handler(_payload_input)

        # Wizard definitions are resolved strictly through WizardService (file_io).
        svc = WizardService()
        text = svc.get_wizard_text(request.wizard_id)
        try:
            wizard_def = yaml.safe_load(text)
        except Exception as e:
            raise RuntimeError(f"invalid wizard yaml: {e}") from e

        await engine.run_wizard(wizard_def)

        job = self._jobs.get_job(job_id)
        job.progress = 1.0
        job.transition(JobState.SUCCEEDED)
        job.finished_at = _utcnow_iso()
        self._jobs.store.save_job(job)
        _LOGGER.info("succeeded")
