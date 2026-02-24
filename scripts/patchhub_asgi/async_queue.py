from __future__ import annotations

import asyncio
import contextlib
import fcntl
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from patchhub.models import JobRecord

from .async_event_pump import start_event_pump
from .async_events_socket import job_socket_path, send_cancel_async
from .async_runner_exec import AsyncRunnerExecutor


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_lock_held_sync(lock_path: Path) -> bool:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = lock_path.open("a+")
    try:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        finally:
            with contextlib.suppress(Exception):
                fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        return False
    finally:
        fd.close()


def _inject_web_overrides(argv: list[str], job_id: str) -> list[str]:
    out = list(argv)

    script_idx = -1
    for i, a in enumerate(out):
        if a.endswith("am_patch.py"):
            script_idx = i
            break

    insert_at = script_idx + 1 if script_idx >= 0 else len(out)

    def _has_override(key: str) -> bool:
        for j in range(len(out) - 1):
            if out[j] == "--override" and out[j + 1].startswith(key + "="):
                return True
        return False

    overrides: list[str] = []
    if not _has_override("patch_layout_json_dir"):
        overrides.extend(["--override", "patch_layout_json_dir=artifacts/web_jobs/" + job_id])

    if not _has_override("ipc_socket_enabled"):
        overrides.extend(["--override", "ipc_socket_enabled=true"])
    if not _has_override("ipc_socket_path"):
        overrides.extend(["--override", f"ipc_socket_path={job_socket_path(job_id)}"])

    if overrides:
        out[insert_at:insert_at] = overrides

    return out


def _persist_job_sync(job_dir: Path, job: JobRecord) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "job.json").write_text(
        json.dumps(job.to_json(), ensure_ascii=True, indent=2), encoding="utf-8"
    )


@dataclass
class QueueState:
    queued: int
    running: int


class AsyncJobQueue:
    def __init__(
        self,
        *,
        repo_root: Path,
        lock_path: Path,
        jobs_root: Path,
        executor: AsyncRunnerExecutor,
    ) -> None:
        self._repo_root = repo_root
        self._lock_path = lock_path
        self._jobs_root = jobs_root
        self._executor = executor

        self._mu = asyncio.Lock()
        self._stop = asyncio.Event()
        self._q: asyncio.Queue[str] = asyncio.Queue()
        self._jobs: dict[str, JobRecord] = {}
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run_loop(), name="patchhub_async_queue")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(Exception):
                await self._task

    async def state(self) -> QueueState:
        async with self._mu:
            running = sum(1 for j in self._jobs.values() if j.status == "running")
            queued = sum(1 for j in self._jobs.values() if j.status == "queued")
        return QueueState(queued=queued, running=running)

    async def list_jobs(self) -> list[JobRecord]:
        async with self._mu:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda j: j.created_utc, reverse=True)
        return jobs

    async def get_job(self, job_id: str) -> JobRecord | None:
        async with self._mu:
            return self._jobs.get(job_id)

    async def enqueue(self, job: JobRecord) -> None:
        async with self._mu:
            self._jobs[job.job_id] = job
            await self._persist(job)
        await self._q.put(job.job_id)

    async def cancel(self, job_id: str) -> bool:
        async with self._mu:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            status = str(job.status)

        if status == "queued":
            async with self._mu:
                job = self._jobs.get(job_id)
                if job is None or job.status != "queued":
                    return False
                job.status = "canceled"
                job.ended_utc = utc_now()
                await self._persist(job)
            return True

        if status == "running":
            now = utc_now()
            async with self._mu:
                job = self._jobs.get(job_id)
                if job is None:
                    return False
                if job.cancel_requested_utc is None:
                    job.cancel_requested_utc = now
                    await self._persist(job)

            sock_ok = await send_cancel_async(job_socket_path(job_id))
            if sock_ok:
                async with self._mu:
                    job = self._jobs.get(job_id)
                    if job is not None:
                        job.cancel_ack_utc = utc_now()
                        job.cancel_source = "socket"
                        await self._persist(job)
                return True

            ok = await self._executor.terminate()
            if ok:
                async with self._mu:
                    job = self._jobs.get(job_id)
                    if job is not None:
                        job.cancel_source = "terminate"
                        await self._persist(job)
            return ok

        return False

    def jobs_root(self) -> Path:
        return self._jobs_root

    def _job_dir(self, job_id: str) -> Path:
        return self._jobs_root / job_id

    async def _persist(self, job: JobRecord) -> None:
        job_dir = self._job_dir(job.job_id)
        await asyncio.to_thread(_persist_job_sync, job_dir, job)

    async def _wait_for_runner_slot(self) -> None:
        while True:
            if self._stop.is_set():
                return
            if await self._executor.is_running():
                await asyncio.sleep(0.25)
                continue

            held = await asyncio.to_thread(is_lock_held_sync, self._lock_path)
            if not held:
                return
            await asyncio.sleep(0.25)

    async def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                job_id = await asyncio.wait_for(self._q.get(), timeout=0.5)
            except TimeoutError:
                continue

            async with self._mu:
                job = self._jobs.get(job_id)
                if job is None:
                    continue

            await self._wait_for_runner_slot()
            if self._stop.is_set():
                return

            async with self._mu:
                job = self._jobs.get(job_id)
                if job is None:
                    continue
                if job.status != "queued":
                    continue
                job.status = "running"
                job.started_utc = utc_now()
                await self._persist(job)

            job_dir = self._job_dir(job_id)
            runner_log = job_dir / "runner.log"

            def _job_jsonl_path(j: JobRecord, job_dir: Path = job_dir) -> Path:
                if j.mode in ("finalize_live", "finalize_workspace"):
                    return job_dir / "am_patch_finalize.jsonl"
                issue_s = str(j.issue_id or "")
                if issue_s.isdigit():
                    return job_dir / ("am_patch_issue_" + issue_s + ".jsonl")
                return job_dir / "am_patch_finalize.jsonl"

            try:
                effective_cmd = _inject_web_overrides(job.canonical_command, job_id)

                sock_path = Path(job_socket_path(job_id))
                sock_path.parent.mkdir(parents=True, exist_ok=True)
                if sock_path.exists() or sock_path.is_symlink():
                    with contextlib.suppress(Exception):
                        sock_path.unlink()

                jsonl_path = _job_jsonl_path(job)
                pump_task = asyncio.create_task(
                    start_event_pump(socket_path=str(sock_path), jsonl_path=jsonl_path),
                    name=f"patchhub_event_pump_{job_id}",
                )

                res = await self._executor.run(
                    effective_cmd, cwd=self._repo_root, log_path=runner_log
                )

                pump_task.cancel()
                with contextlib.suppress(Exception):
                    await pump_task

                async with self._mu:
                    job = self._jobs.get(job_id)
                    if job is None:
                        continue
                    job.return_code = res.return_code
                    if job.status == "canceled":
                        job.ended_utc = job.ended_utc or utc_now()
                    elif res.return_code == 0:
                        job.status = "success"
                        job.ended_utc = utc_now()
                    else:
                        job.status = "fail"
                        job.ended_utc = utc_now()
                    await self._persist(job)
            except Exception as e:
                async with self._mu:
                    job = self._jobs.get(job_id)
                    if job is None:
                        continue
                    job.status = "fail" if job.status != "canceled" else job.status
                    job.ended_utc = utc_now()
                    job.error = f"{type(e).__name__}: {e}"
                    await self._persist(job)
