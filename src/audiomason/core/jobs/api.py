from __future__ import annotations

from datetime import UTC, datetime

from audiomason.core.jobs.model import Job, JobState, JobType
from audiomason.core.jobs.store import JobStore


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


class JobService:
    def __init__(self, store: JobStore | None = None) -> None:
        self._store = store if store is not None else JobStore()

    @property
    def store(self) -> JobStore:
        return self._store

    def create_job(self, job_type: JobType, meta: dict[str, str] | None = None) -> Job:
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
        return job

    def get_job(self, job_id: str) -> Job:
        return self._store.load_job(job_id)

    def list_jobs(self) -> list[Job]:
        return self._store.list_jobs()

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
