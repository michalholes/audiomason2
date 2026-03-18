"""Detached authority worker for PROCESS contract jobs.

ASCII-only.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import fcntl
from collections.abc import Iterator
from importlib import import_module
from pathlib import Path
from typing import Any

from audiomason.core.jobs.api import JobService
from audiomason.core.jobs.model import JobState, JobType
from audiomason.core.jobs.store import JobStore
from audiomason.core.orchestration import OP_RUN_JOB, Orchestrator, _emit_diag, _utcnow_iso
from audiomason.core.orchestration_models import ProcessContractRequest
from audiomason.core.process_job_contracts import resolve_process_job_contract


class _ClaimedJob(contextlib.AbstractContextManager[bool]):
    def __init__(self, path: Path) -> None:
        self._path = path
        self._fd: Any | None = None

    def __enter__(self) -> bool:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = self._path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self._fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._fd.close()
            self._fd = None
            return False
        return True

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._fd is None:
            return None
        with contextlib.suppress(OSError):
            fcntl.flock(self._fd.fileno(), fcntl.LOCK_UN)
        self._fd.close()
        self._fd = None
        return None


def _candidate_job_ids(store: JobStore, *, job_id: str | None) -> Iterator[str]:
    if job_id is not None:
        yield job_id
        return
    yield from store.list_job_ids()


def _mark_job_running(orch: Orchestrator, job_id: str) -> None:
    job = orch.get_job(job_id)
    if job.state != JobState.PENDING:
        return
    job.transition(JobState.RUNNING)
    job.started_at = _utcnow_iso()
    orch.jobs.store.save_job(job)
    orch.jobs.append_log_line(job_id, "started")
    _emit_diag(
        "diag.job.start",
        operation=OP_RUN_JOB,
        data={"job_id": job_id, "job_type": "process", "status": "running"},
    )


def _build_request(job_meta: dict[str, str]) -> ProcessContractRequest:
    contract = resolve_process_job_contract(job_meta)
    if contract is None:
        raise RuntimeError("unsupported process contract")
    try:
        request_meta = contract.bind_job_meta(job_meta)
    except ValueError as e:
        raise RuntimeError("unsupported or incomplete process contract") from e

    helper = import_module("plugins.import.engine_diagnostics_required")
    build_loader = helper.build_process_contract_plugin_loader
    plugin_loader = build_loader(job_meta=dict(job_meta))
    return ProcessContractRequest(
        contract_id=contract.contract_id,
        plugin_name=contract.plugin_name,
        entrypoint_name=contract.entrypoint_name,
        plugin_loader=plugin_loader,
        job_meta=request_meta,
    )


def _run_claimed_job(orch: Orchestrator, job_id: str) -> None:
    job = orch.get_job(job_id)
    if job.type != JobType.PROCESS:
        return
    if job.state not in {JobState.PENDING, JobState.RUNNING}:
        return
    contract = resolve_process_job_contract(job.meta)
    if contract is None:
        return
    if not str(job.meta.get("detached_runtime_json") or ""):
        return

    _mark_job_running(orch, job_id)
    request = _build_request(dict(job.meta))
    asyncio.run(orch._run_process_contract_job(job_id, request))


def _process_job(store: JobStore, *, job_id: str) -> None:
    claim = _ClaimedJob(store.job_dir(job_id) / "process_contract.claim")
    with claim as claimed:
        if not claimed:
            return
        orch = Orchestrator(job_service=JobService(store=store))
        try:
            _run_claimed_job(orch, job_id)
        except Exception as e:
            job = orch.get_job(job_id)
            if job.state == JobState.PENDING:
                job.transition(JobState.RUNNING)
                job.started_at = _utcnow_iso()
            if job.state == JobState.RUNNING:
                job.transition(JobState.FAILED)
                job.error = str(e)
                job.finished_at = _utcnow_iso()
                orch.jobs.store.save_job(job)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs-root", required=True)
    parser.add_argument("--job-id")
    parser.add_argument("--adopt-all", action="store_true")
    args = parser.parse_args()

    store = JobStore(root=Path(args.jobs_root))
    if args.job_id and not args.adopt_all:
        _process_job(store, job_id=str(args.job_id))
        return 0

    for job_id in _candidate_job_ids(store, job_id=str(args.job_id) if args.job_id else None):
        _process_job(store, job_id=job_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
