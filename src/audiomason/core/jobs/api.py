from __future__ import annotations

import contextlib
import time
from datetime import UTC, datetime
from typing import Any

from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus
from audiomason.core.jobs.model import Job, JobState, JobType
from audiomason.core.jobs.store import JobStore
from audiomason.core.logging import get_logger

_LOGGER = get_logger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _duration_ms(t0: float, t1: float) -> int:
    ms = int((t1 - t0) * 1000.0)
    return 0 if ms < 0 else ms


def _params_summary(meta: dict[str, str] | None) -> dict[str, Any]:
    meta = dict(meta or {})
    # Never emit large payloads. Summarize keys + a few selected safe values.
    keys = sorted(meta.keys())
    sample: dict[str, Any] = {}
    for k in keys[:8]:
        v = meta.get(k)
        if v is None:
            continue
        s = str(v)
        sample[k] = s if len(s) <= 120 else (s[:117] + "...")
    return {"meta_keys": keys, "meta_sample": sample}


def _emit_diag(event: str, *, operation: str, data: dict[str, Any]) -> None:
    # Fail-safe: diagnostics must not affect runtime behavior.
    with contextlib.suppress(Exception):
        envelope = build_envelope(event=event, component="jobs", operation=operation, data=data)
        get_event_bus().publish(event, envelope)


def _emit_op_start(operation: str, data: dict[str, Any]) -> None:
    _emit_diag("operation.start", operation=operation, data=data)


def _emit_op_end(operation: str, data: dict[str, Any]) -> None:
    _emit_diag("operation.end", operation=operation, data=data)


class JobService:
    def __init__(self, store: JobStore | None = None) -> None:
        self._store = store if store is not None else JobStore()

    @property
    def store(self) -> JobStore:
        return self._store

    def create_job(self, job_type: JobType, meta: dict[str, str] | None = None) -> Job:
        t0 = time.monotonic()
        _emit_op_start(
            "jobs.create",
            {
                "job_type": job_type.value,
                "state": JobState.PENDING.value,
                "progress": 0.0,
                "params_summary": _params_summary(meta),
            },
        )

        job_id = self._store.next_job_id()
        now = _utcnow_iso()
        job = Job(
            job_id=job_id,
            type=job_type,
            state=JobState.PENDING,
            progress=0.0,
            created_at=now,
            meta=dict(meta or {}),
        )
        self._store.save_job(job)

        # Ensure log exists
        log_path = self._store.job_log_path(job_id)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if not log_path.exists():
            log_path.write_text("", encoding="utf-8")

        data = {
            "job_id": job_id,
            "job_type": job_type.value,
            "state": job.state.value,
            "progress": job.progress,
            "params_summary": _params_summary(meta),
            "status": "ok",
        }
        _emit_diag("jobs.create", operation="jobs.create", data=data)
        _emit_op_end(
            "jobs.create",
            {
                **data,
                "duration_ms": _duration_ms(t0, time.monotonic()),
            },
        )
        _LOGGER.info(f"job created: job_id={job_id} type={job_type.value} state={job.state.value}")
        return job

    def get_job(self, job_id: str) -> Job:
        t0 = time.monotonic()
        _emit_op_start("jobs.get", {"job_id": job_id})
        job = self._store.load_job(job_id)
        data = {
            "job_id": job.job_id,
            "job_type": job.type.value,
            "state": job.state.value,
            "progress": job.progress,
            "status": "ok",
        }
        _emit_diag("jobs.get", operation="jobs.get", data=data)
        _emit_op_end(
            "jobs.get",
            {
                **data,
                "duration_ms": _duration_ms(t0, time.monotonic()),
            },
        )
        return job

    def list_jobs(self) -> list[Job]:
        t0 = time.monotonic()
        _emit_op_start("jobs.list", {})
        jobs = self._store.list_jobs()
        data = {
            "count": len(jobs),
            "status": "ok",
        }
        _emit_diag("jobs.list", operation="jobs.list", data=data)
        _emit_op_end(
            "jobs.list",
            {
                **data,
                "duration_ms": _duration_ms(t0, time.monotonic()),
            },
        )
        return jobs

    def read_log(
        self, job_id: str, offset: int = 0, limit_bytes: int = 64 * 1024
    ) -> tuple[str, int]:
        path = self._store.job_log_path(job_id)
        if not path.exists():
            return ("", offset)
        data = path.read_bytes()
        if offset < 0:
            offset = 0
        chunk = data[offset : offset + limit_bytes]
        text = chunk.decode("utf-8", errors="replace")
        return (text, offset + len(chunk))

    def append_log_line(self, job_id: str, line: str) -> None:
        path = self._store.job_log_path(job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line.rstrip("\n") + "\n")

    def cancel_job(self, job_id: str) -> Job:
        job = self._store.load_job(job_id)
        now = _utcnow_iso()

        if job.state in {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED}:
            return job

        if job.state == JobState.PENDING:
            job.transition(JobState.CANCELLED)
            job.finished_at = now
            self._store.save_job(job)
            self.append_log_line(job_id, "cancelled")
            return job

        # RUNNING
        job.cancel_requested = True
        self._store.save_job(job)
        self.append_log_line(job_id, "cancel requested")
        return job
