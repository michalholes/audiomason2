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
import threading
import time
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from audiomason.core.config import ConfigResolver
from audiomason.core.context import ProcessingContext
from audiomason.core.diagnostics import build_envelope
from audiomason.core.errors import ConfigError
from audiomason.core.events import get_event_bus
from audiomason.core.jobs.api import JobService
from audiomason.core.jobs.model import Job, JobState, JobType
from audiomason.core.logging import (
    VerbosityLevel,
    get_log_sink,
    get_logger,
    set_log_sink,
    set_verbosity,
)
from audiomason.core.orchestration_models import ProcessContractRequest, ProcessRequest
from audiomason.core.phase import PhaseContractError, PhaseGuard
from audiomason.core.pipeline import PipelineExecutor
from audiomason.core.process_contract_runtime import get_process_contract_runtime
from audiomason.core.process_job_contracts import resolve_process_job_contract


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


_LOGGER = get_logger(__name__)


COMPONENT = "orchestration"
OP_RUN_JOB = "run_job"
OP_CTX = "context_lifecycle"
OP_EXECUTE_PIPELINE = "execute_pipeline"


def _emit_diag(event: str, *, operation: str, data: dict[str, Any]) -> None:
    """Emit a structured runtime diagnostic event via the authoritative entrypoint.

    This must never crash or block processing.
    """
    try:
        envelope = build_envelope(
            event=event,
            component=COMPONENT,
            operation=operation,
            data=data,
        )
        get_event_bus().publish(event, envelope)
    except Exception as e:
        _LOGGER.warning(f"diagnostic emission failed: {type(e).__name__}: {e}")


def _parse_verbosity(value: object) -> VerbosityLevel:
    if isinstance(value, VerbosityLevel):
        return value
    if isinstance(value, int):
        try:
            return VerbosityLevel(value)
        except ValueError as e:
            raise ConfigError(f"Invalid logging.level integer: {value}") from e
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
        if v in mapping:
            return mapping[v]
        raise ConfigError(f"Invalid logging.level string: {value!r}")
    raise ConfigError(f"Invalid logging.level type: {type(value).__name__}")


def _resolve_effective_verbosity() -> VerbosityLevel:
    resolver = ConfigResolver()
    value = resolver.resolve_logging_level()
    return _parse_verbosity(value)


def _duration_ms(start: float, end: float) -> int:
    return int((end - start) * 1000)


def _run_coro_sync(coro: Coroutine[Any, Any, Any]) -> None:
    """Run a coroutine to completion in a dedicated event loop.

    This is used only when no running event loop exists (e.g., CLI code paths).
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(coro)
        loop.run_until_complete(loop.shutdown_asyncgens())
    finally:
        asyncio.set_event_loop(None)
        loop.close()


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
        _emit_diag(
            "diag.job.start",
            operation=OP_RUN_JOB,
            data={"job_id": job.job_id, "job_type": "process", "status": "running"},
        )

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
            _run_coro_sync(self._run_process_job(job.job_id, request))
        else:
            loop.create_task(self._run_process_job(job.job_id, request))

        return job.job_id

    def run_job(self, job_id: str, *, plugin_loader: Any, verbosity: int = 1) -> None:
        """Run an existing PENDING job."""
        job = self._jobs.get_job(job_id)
        if job.state != JobState.PENDING:
            raise RuntimeError("job is not pending")

        if job.type == JobType.PROCESS:
            contract = resolve_process_job_contract(job.meta)
            if contract is not None:
                if plugin_loader is None:
                    raise RuntimeError("plugin_loader is required for process contract jobs")
                request = self._build_process_contract_request(
                    job,
                    plugin_loader=plugin_loader,
                    verbosity=verbosity,
                )
                self._run_local_process_contract_job(
                    job=job,
                    request=request,
                    verbosity=verbosity,
                )
                return

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
                _run_coro_sync(self._run_process_job(job.job_id, process_request))
            else:
                loop.create_task(self._run_process_job(job.job_id, process_request))
            return

        raise RuntimeError(f"unsupported job type: {job.type}")

    def _run_local_process_contract_job(
        self,
        *,
        job: Job,
        request: ProcessContractRequest,
        verbosity: int,
    ) -> None:
        job.transition(JobState.RUNNING)
        job.started_at = _utcnow_iso()
        job.meta["verbosity_override"] = str(int(verbosity))
        self._jobs.store.save_job(job)
        _emit_diag(
            "diag.job.start",
            operation=OP_RUN_JOB,
            data={"job_id": job.job_id, "job_type": "process", "status": "running"},
        )

        prev_sink = get_log_sink()
        set_log_sink(lambda line: self._jobs.append_log_line(job.job_id, line))
        try:
            _LOGGER.info("started")
        finally:
            set_log_sink(prev_sink)

        def runner() -> None:
            _run_coro_sync(self._run_process_contract_job(job.job_id, request))

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            runner()
        else:
            thread = threading.Thread(target=runner, name=f"job-{job.job_id}-contract")
            thread.start()

    def _build_process_contract_request(
        self,
        job: Job,
        *,
        plugin_loader: Any,
        verbosity: int,
    ) -> ProcessContractRequest:
        contract = resolve_process_job_contract(job.meta)
        if contract is None:
            raise RuntimeError("unsupported process contract")
        meta = dict(job.meta)
        meta["verbosity_override"] = str(int(verbosity))
        try:
            request_meta = contract.bind_job_meta(meta)
        except ValueError as e:
            raise RuntimeError("unsupported or incomplete process contract") from e
        return ProcessContractRequest(
            contract_id=contract.contract_id,
            plugin_name=contract.plugin_name,
            entrypoint_name=contract.entrypoint_name,
            plugin_loader=plugin_loader,
            job_meta=request_meta,
        )

    def submit_process_contract_job(self, job_id: str, *, verbosity: int = 1) -> None:
        job = self._jobs.get_job(job_id)
        if job.state != JobState.PENDING:
            raise RuntimeError("job is not pending")
        if job.type != JobType.PROCESS:
            raise RuntimeError(f"unsupported job type: {job.type}")
        contract = resolve_process_job_contract(job.meta)
        if contract is None:
            raise RuntimeError("unsupported process contract")

        job.meta["verbosity_override"] = str(int(verbosity))
        try:
            contract.bind_job_meta(job.meta)
        except ValueError as e:
            job.meta.pop("verbosity_override", None)
            raise RuntimeError("unsupported or incomplete process contract") from e
        self._jobs.store.save_job(job)

        get_process_contract_runtime().submit(
            job_id=job.job_id,
            jobs_root=self._jobs.store.root,
        )

    def start_process_runtime(
        self, *, plugin_loader: Any | None = None, verbosity: int = 1
    ) -> None:
        if plugin_loader is not None:
            for job in self._jobs.list_jobs():
                if job.type != JobType.PROCESS:
                    continue
                if job.state != JobState.PENDING:
                    continue
                if resolve_process_job_contract(job.meta) is None:
                    continue
                if str(job.meta.get("detached_runtime_json") or ""):
                    continue
                request = self._build_process_contract_request(
                    job,
                    plugin_loader=plugin_loader,
                    verbosity=verbosity,
                )
                self._run_local_process_contract_job(
                    job=job,
                    request=request,
                    verbosity=verbosity,
                )
        get_process_contract_runtime().start(jobs_root=self._jobs.store.root)

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

    async def _run_process_contract_job(self, job_id: str, request: ProcessContractRequest) -> None:
        prev_sink = get_log_sink()
        set_log_sink(lambda line: self._jobs.append_log_line(job_id, line))
        set_verbosity(_resolve_effective_verbosity())
        start_time = time.monotonic()
        try:
            job = self._jobs.get_job(job_id)
            override = job.meta.get("verbosity_override")
            if isinstance(override, str) and override.isdigit():
                set_verbosity(_parse_verbosity(int(override)))

            with PhaseGuard.processing():
                plugin = request.plugin_loader.get_plugin(request.plugin_name)
                handler = getattr(plugin, request.entrypoint_name)
                _emit_diag(
                    "diag.boundary.start",
                    operation=OP_EXECUTE_PIPELINE,
                    data={
                        "job_id": job_id,
                        "contract_id": request.contract_id,
                        "plugin_name": request.plugin_name,
                    },
                )
                try:
                    result = handler(
                        job_id=job_id,
                        job_meta=dict(request.job_meta),
                        plugin_loader=request.plugin_loader,
                    )
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    _emit_diag(
                        "diag.boundary.fail",
                        operation=OP_EXECUTE_PIPELINE,
                        data={
                            "job_id": job_id,
                            "contract_id": request.contract_id,
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                        },
                    )
                    raise
                else:
                    _emit_diag(
                        "diag.boundary.end",
                        operation=OP_EXECUTE_PIPELINE,
                        data={
                            "job_id": job_id,
                            "contract_id": request.contract_id,
                            "status": "succeeded",
                        },
                    )

            job = self._jobs.get_job(job_id)
            job.progress = 1.0
            job.transition(JobState.SUCCEEDED)
            job.finished_at = _utcnow_iso()
            self._jobs.store.save_job(job)
            _emit_diag(
                "diag.job.end",
                operation=OP_RUN_JOB,
                data={
                    "job_id": job_id,
                    "job_type": "process",
                    "status": "succeeded",
                    "duration_ms": _duration_ms(start_time, time.monotonic()),
                },
            )
            _LOGGER.info("succeeded")
        except PhaseContractError as e:
            job = self._jobs.get_job(job_id)
            job.transition(JobState.FAILED)
            job.error = str(e)
            job.finished_at = _utcnow_iso()
            self._jobs.store.save_job(job)
            _emit_diag(
                "diag.job.end",
                operation=OP_RUN_JOB,
                data={
                    "job_id": job_id,
                    "job_type": "process",
                    "status": "failed",
                    "duration_ms": _duration_ms(start_time, time.monotonic()),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            _LOGGER.error(f"failed: {e}")
        except Exception as e:
            job = self._jobs.get_job(job_id)
            job.transition(JobState.FAILED)
            job.error = str(e)
            job.finished_at = _utcnow_iso()
            self._jobs.store.save_job(job)
            _emit_diag(
                "diag.boundary.end",
                operation=OP_EXECUTE_PIPELINE,
                data={
                    "job_id": job_id,
                    "status": "failed",
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            _emit_diag(
                "diag.job.end",
                operation=OP_RUN_JOB,
                data={
                    "job_id": job_id,
                    "job_type": "process",
                    "status": "failed",
                    "duration_ms": _duration_ms(start_time, time.monotonic()),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            _LOGGER.error(f"failed: {e}")
        finally:
            set_log_sink(prev_sink)

    async def _run_process_job(self, job_id: str, request: ProcessRequest) -> None:
        prev_sink = get_log_sink()
        set_log_sink(lambda line: self._jobs.append_log_line(job_id, line))
        set_verbosity(_resolve_effective_verbosity())
        start_time = time.monotonic()
        try:
            job = self._jobs.get_job(job_id)
            override = job.meta.get("verbosity_override")
            if isinstance(override, str) and override.isdigit():
                set_verbosity(_parse_verbosity(int(override)))

            with PhaseGuard.processing():
                try:
                    await self._run_process_job_impl(job_id, request, start_time=start_time)
                except PhaseContractError as e:
                    job = self._jobs.get_job(job_id)
                    job.transition(JobState.FAILED)
                    job.error = str(e)
                    job.finished_at = _utcnow_iso()
                    self._jobs.store.save_job(job)
                    _emit_diag(
                        "diag.job.end",
                        operation=OP_RUN_JOB,
                        data={
                            "job_id": job_id,
                            "job_type": "process",
                            "status": "failed",
                            "duration_ms": _duration_ms(start_time, time.monotonic()),
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                        },
                    )
                    _LOGGER.error(f"failed: {e}")
                except Exception as e:
                    job = self._jobs.get_job(job_id)
                    job.transition(JobState.FAILED)
                    job.error = str(e)
                    job.finished_at = _utcnow_iso()
                    self._jobs.store.save_job(job)
                    _emit_diag(
                        "diag.job.end",
                        operation=OP_RUN_JOB,
                        data={
                            "job_id": job_id,
                            "job_type": "process",
                            "status": "failed",
                            "duration_ms": _duration_ms(start_time, time.monotonic()),
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                        },
                    )
                    _LOGGER.error(f"failed: {e}")
                else:
                    # Success path is responsible for emitting diag.job.end.
                    pass
        finally:
            set_log_sink(prev_sink)

    async def _run_process_job_impl(
        self, job_id: str, request: ProcessRequest, *, start_time: float
    ) -> None:
        contexts = request.contexts
        total = max(1, len(contexts))
        executor = PipelineExecutor(request.plugin_loader)

        for i, ctx in enumerate(contexts, 1):
            job = self._jobs.get_job(job_id)
            if job.cancel_requested:
                job.transition(JobState.CANCELLED)
                job.finished_at = _utcnow_iso()
                self._jobs.store.save_job(job)
                _emit_diag(
                    "diag.job.end",
                    operation=OP_RUN_JOB,
                    data={
                        "job_id": job_id,
                        "job_type": "process",
                        "status": "cancelled",
                        "duration_ms": _duration_ms(start_time, time.monotonic()),
                    },
                )
                _LOGGER.warning("cancelled")
                return

            _LOGGER.info(f"processing: {ctx.source}")

            _emit_diag(
                "diag.ctx.start",
                operation=OP_CTX,
                data={
                    "job_id": job_id,
                    "context_index": i,
                    "context_total": total,
                    "source": str(ctx.source),
                },
            )

            _emit_diag(
                "diag.boundary.start",
                operation=OP_EXECUTE_PIPELINE,
                data={
                    "job_id": job_id,
                    "pipeline_path": str(request.pipeline_path),
                    "source": str(ctx.source),
                },
            )

            try:
                await executor.execute_from_yaml(request.pipeline_path, ctx)
            except Exception as e:
                _emit_diag(
                    "diag.boundary.fail",
                    operation=OP_EXECUTE_PIPELINE,
                    data={
                        "job_id": job_id,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    },
                )
                _emit_diag(
                    "diag.boundary.end",
                    operation=OP_EXECUTE_PIPELINE,
                    data={
                        "job_id": job_id,
                        "pipeline_path": str(request.pipeline_path),
                        "status": "failed",
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    },
                )
                _emit_diag(
                    "diag.ctx.end",
                    operation=OP_CTX,
                    data={
                        "job_id": job_id,
                        "context_index": i,
                        "context_total": total,
                        "source": str(ctx.source),
                        "status": "failed",
                    },
                )
                raise
            else:
                _emit_diag(
                    "diag.boundary.end",
                    operation=OP_EXECUTE_PIPELINE,
                    data={
                        "job_id": job_id,
                        "pipeline_path": str(request.pipeline_path),
                        "status": "succeeded",
                    },
                )
                _emit_diag(
                    "diag.ctx.end",
                    operation=OP_CTX,
                    data={
                        "job_id": job_id,
                        "context_index": i,
                        "context_total": total,
                        "source": str(ctx.source),
                        "status": "succeeded",
                    },
                )

            job = self._jobs.get_job(job_id)
            job.progress = float(i) / float(total)
            self._jobs.store.save_job(job)

        job = self._jobs.get_job(job_id)
        job.progress = 1.0
        job.transition(JobState.SUCCEEDED)
        job.finished_at = _utcnow_iso()
        self._jobs.store.save_job(job)
        _emit_diag(
            "diag.job.end",
            operation=OP_RUN_JOB,
            data={
                "job_id": job_id,
                "job_type": "process",
                "status": "succeeded",
                "duration_ms": _duration_ms(start_time, time.monotonic()),
            },
        )
        _LOGGER.info("succeeded")
