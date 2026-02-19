from __future__ import annotations

import contextlib
import fcntl
import json
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .models import JobRecord
from .runner_exec import RunnerExecutor


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_lock_held(lock_path: Path) -> bool:
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
    """Return argv with web-required runner overrides injected.

    Web requires runner NDJSON output (json_out=true) and a job-local json dir
    (patch_layout_json_dir=artifacts/web_jobs/<job_id>).

    This function is deterministic and idempotent.
    """

    out = list(argv)

    # Find the runner script path (usually scripts/am_patch.py).
    script_idx = -1
    for i, a in enumerate(out):
        if a.endswith("am_patch.py"):
            script_idx = i
            break

    # If script is not found, append overrides at the end.
    insert_at = script_idx + 1 if script_idx >= 0 else len(out)

    def _has_override(key: str) -> bool:
        for j in range(len(out) - 1):
            if out[j] == "--override" and out[j + 1].startswith(key + "="):
                return True
        return False

    overrides: list[str] = []
    if not _has_override("json_out"):
        overrides.extend(["--override", "json_out=true"])
    if not _has_override("patch_layout_json_dir"):
        overrides.extend(
            [
                "--override",
                "patch_layout_json_dir=artifacts/web_jobs/" + job_id,
            ]
        )

    if overrides:
        out[insert_at:insert_at] = overrides

    return out


@dataclass
class QueueState:
    queued: int
    running: int


class JobQueue:
    def __init__(
        self,
        repo_root: Path,
        lock_path: Path,
        jobs_root: Path,
        executor: RunnerExecutor,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self._repo_root = repo_root
        self._lock_path = lock_path
        self._jobs_root = jobs_root
        self._executor = executor
        self._on_change = on_change

        self._mu = threading.Lock()
        self._cv = threading.Condition(self._mu)
        self._stop = False
        self._queue: list[str] = []
        self._jobs: dict[str, JobRecord] = {}
        self._worker = threading.Thread(target=self._run_loop, daemon=True)
        self._worker.start()

    def state(self) -> QueueState:
        with self._mu:
            running = sum(1 for j in self._jobs.values() if j.status == "running")
            return QueueState(queued=len(self._queue), running=running)

    def list_jobs(self) -> list[JobRecord]:
        with self._mu:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda j: j.created_utc, reverse=True)
        return jobs

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._mu:
            return self._jobs.get(job_id)

    def enqueue(self, job: JobRecord) -> None:
        with self._mu:
            self._jobs[job.job_id] = job
            self._queue.append(job.job_id)
            self._persist(job)
            self._cv.notify_all()
        self._changed()

    def cancel(self, job_id: str) -> bool:
        with self._mu:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job.status == "queued":
                job.status = "canceled"
                job.ended_utc = utc_now()
                self._persist(job)
                self._queue = [j for j in self._queue if j != job_id]
                self._cv.notify_all()
                self._changed()
                return True
            if job.status == "running":
                ok = self._executor.terminate()
                if ok:
                    job.status = "canceled"
                    job.ended_utc = utc_now()
                    self._persist(job)
                    self._changed()
                return ok
            return False

    def stop(self) -> None:
        with self._mu:
            self._stop = True
            self._cv.notify_all()
        self._worker.join(timeout=2)

    def jobs_root(self) -> Path:
        return self._jobs_root

    def _changed(self) -> None:
        if self._on_change is not None:
            with contextlib.suppress(Exception):
                self._on_change()

    def _job_dir(self, job_id: str) -> Path:
        return self._jobs_root / job_id

    def _persist(self, job: JobRecord) -> None:
        d = self._job_dir(job.job_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / "job.json").write_text(
            json.dumps(job.to_json(), ensure_ascii=True, indent=2), encoding="utf-8"
        )

    def _run_loop(self) -> None:
        while True:
            with self._mu:
                while not self._stop and not self._queue:
                    self._cv.wait(timeout=0.5)
                if self._stop:
                    return
                job_id = self._queue[0]
                job = self._jobs.get(job_id)
                if job is None:
                    self._queue.pop(0)
                    continue

            # Wait for runner lock to be free and executor to be idle.
            while True:
                if self._stop:
                    return
                if not self._executor.is_running() and not is_lock_held(self._lock_path):
                    break
                time.sleep(0.25)

            with self._mu:
                if job.status != "queued":
                    # canceled while waiting
                    if self._queue and self._queue[0] == job_id:
                        self._queue.pop(0)
                    continue
                job.status = "running"
                job.started_utc = utc_now()
                self._persist(job)
            self._changed()

            job_dir = self._job_dir(job_id)
            runner_log = job_dir / "runner.log"

            try:
                effective_cmd = _inject_web_overrides(job.canonical_command, job_id)
                res = self._executor.run(effective_cmd, cwd=self._repo_root, log_path=runner_log)
                with self._mu:
                    job.return_code = res.return_code
                    if job.status == "canceled":
                        job.ended_utc = job.ended_utc or utc_now()
                    elif res.return_code == 0:
                        job.status = "success"
                        job.ended_utc = utc_now()
                    else:
                        job.status = "fail"
                        job.ended_utc = utc_now()
                    self._persist(job)
            except Exception as e:
                with self._mu:
                    job.status = "fail" if job.status != "canceled" else job.status
                    job.ended_utc = utc_now()
                    job.error = f"{type(e).__name__}: {e}"
                    self._persist(job)
            finally:
                with self._mu:
                    if self._queue and self._queue[0] == job_id:
                        self._queue.pop(0)
                self._changed()


def new_job_id() -> str:
    return uuid.uuid4().hex
