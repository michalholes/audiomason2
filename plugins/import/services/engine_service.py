"""Import engine service facade.

This is the stable service API callable from CLI without any web dependency.

ASCII-only.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus
from audiomason.core.jobs.api import JobService
from audiomason.core.jobs.model import JobState, JobType
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

from ..engine.queue_store import ImportQueueStore
from ..engine.types import BookDecision, ImportJobRequest, ImportQueueState
from ..job_handlers.import_job import run_import_job
from ..preflight.types import PreflightResult
from ..processed_registry.service import ProcessedRegistry
from ..session_store.service import ImportRunStateStore
from ..session_store.types import ImportRunState


def _emit_diag(event: str, *, operation: str, data: dict[str, Any]) -> None:
    try:
        env = build_envelope(
            event=event,
            component="import.engine.service",
            operation=operation,
            data=data,
        )
        get_event_bus().publish(event, env)
    except Exception:
        return


class ImportEngineService:
    """Import processing engine (PHASE 2) persisted Jobs."""

    def __init__(self, *, fs: FileService, jobs: JobService | None = None) -> None:
        self._fs = fs
        self._jobs = jobs if jobs is not None else JobService()
        self._run_store = ImportRunStateStore(fs)
        self._registry = ProcessedRegistry(fs)
        self._queue = ImportQueueStore(fs)

    @property
    def jobs(self) -> JobService:
        return self._jobs

    def resolve_book_decisions(
        self, *, preflight: PreflightResult, state: ImportRunState
    ) -> list[BookDecision]:
        """Resolve non-interactive decisions for PHASE 2 from PHASE 0 + PHASE 1 state."""
        _emit_diag(
            "boundary.start",
            operation="resolve_book_decisions",
            data={"books_n": len(preflight.books), "mode": state.source_handling_mode},
        )

        decisions: list[BookDecision] = []
        for b in preflight.books:
            decisions.append(
                BookDecision(
                    book_rel_path=b.rel_path,
                    author=b.suggested_author or b.author,
                    title=b.suggested_title or b.book,
                    handling_mode=state.source_handling_mode,
                    options=state.global_options,
                )
            )

        decisions.sort(key=lambda d: d.book_rel_path)
        _emit_diag(
            "boundary.end",
            operation="resolve_book_decisions",
            data={"status": "succeeded", "decisions_n": len(decisions)},
        )
        return decisions

    def start_import_job(self, request: ImportJobRequest) -> list[str]:
        """Create persisted Jobs for PHASE 2 import processing."""
        _emit_diag(
            "boundary.start",
            operation="start_import_job",
            data={"run_id": request.run_id, "decisions_n": len(request.decisions)},
        )

        # Persist state for later CLI/Web access.
        self._run_store.put(request.run_id, request.state)

        created: list[str] = []
        for dec in sorted(request.decisions, key=lambda d: d.book_rel_path):
            job = self._jobs.create_job(
                JobType.PROCESS,
                meta={
                    "kind": "import",
                    "run_id": request.run_id,
                    "source_root": request.source_root,
                    "book_rel_path": dec.book_rel_path,
                    "mode": str(request.state.source_handling_mode),
                    "decision_json": json.dumps(
                        asdict(dec), ensure_ascii=True, separators=(",", ":"), sort_keys=True
                    ),
                },
            )
            created.append(job.job_id)

        _emit_diag(
            "boundary.end",
            operation="start_import_job",
            data={"status": "succeeded", "jobs_n": len(created)},
        )
        return created

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        job = self._jobs.get_job(job_id)
        return job.to_dict()

    def retry_failed_jobs(self, *, run_id: str) -> list[str]:
        """Create new jobs for failed import jobs in the run."""
        _emit_diag("boundary.start", operation="retry_failed_jobs", data={"run_id": run_id})

        new_jobs: list[str] = []
        for job in self._jobs.list_jobs():
            if job.meta.get("kind") != "import":
                continue
            if job.meta.get("run_id") != run_id:
                continue
            if job.state != JobState.FAILED:
                continue
            meta = dict(job.meta)
            meta["retry_of"] = job.job_id
            meta.pop("error", None)
            new = self._jobs.create_job(JobType.PROCESS, meta=meta)
            new_jobs.append(new.job_id)

        _emit_diag(
            "boundary.end",
            operation="retry_failed_jobs",
            data={"status": "succeeded", "jobs_n": len(new_jobs)},
        )
        return new_jobs

    def pause_queue(self) -> None:
        state = self._queue.load()
        self._queue.save(ImportQueueState(mode="paused"))
        _emit_diag(
            "diag.queue",
            operation="pause_queue",
            data={"from": state.mode, "to": "paused"},
        )

    def resume_queue(self) -> None:
        state = self._queue.load()
        self._queue.save(ImportQueueState(mode="running"))
        _emit_diag(
            "diag.queue",
            operation="resume_queue",
            data={"from": state.mode, "to": "running"},
        )

    def run_pending(self, *, limit: int = 1) -> list[str]:
        """Run up to N pending import jobs if queue is running.

        This method is sync and deterministic and is intended to be called by
        CLI or a daemon.
        """
        q = self._queue.load()
        if q.mode != "running":
            return []

        ran: list[str] = []
        for job in self._jobs.list_jobs():
            if len(ran) >= limit:
                break
            if job.meta.get("kind") != "import":
                continue
            if job.state != JobState.PENDING:
                continue

            run_id = job.meta.get("run_id", "")
            state = self._run_store.get(run_id)
            if state is None:
                # Cannot run without persisted state.
                job.error = "Missing ImportRunState"
                job.state = JobState.FAILED
                self._jobs.store.save_job(job)
                continue

            source_root = RootName(str(job.meta.get("source_root", RootName.INBOX.value)))
            book_rel_path = str(job.meta.get("book_rel_path", ""))

            # Transition to RUNNING
            job.transition(JobState.RUNNING)
            self._jobs.store.save_job(job)

            run_import_job(
                job_id=job.job_id,
                job_service=self._jobs,
                fs=self._fs,
                registry=self._registry,
                run_state=state,
                source_root=source_root,
                book_rel_path=book_rel_path,
            )
            ran.append(job.job_id)

        return ran
