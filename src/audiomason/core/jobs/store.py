from __future__ import annotations

import contextlib
import json
import time
from pathlib import Path
from typing import Any

from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus
from audiomason.core.jobs.model import Job, JobState
from audiomason.core.jobs.paths import jobs_root
from audiomason.core.logging import get_logger

_LOGGER = get_logger(__name__)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _duration_ms(t0: float, t1: float) -> int:
    ms = int((t1 - t0) * 1000.0)
    return 0 if ms < 0 else ms


def _shorten_text(s: str, *, max_chars: int = 2000) -> str:
    if len(s) <= max_chars:
        return s
    return s[: max(0, max_chars - 3)] + "..."


def _shorten_traceback(tb: str) -> str:
    tb = tb.strip("\n")
    if not tb:
        return ""
    lines = tb.splitlines()
    # Keep last N lines (most relevant).
    lines = lines[-20:]
    return _shorten_text("\n".join(lines), max_chars=2000)


def _emit_diag(event: str, *, operation: str, data: dict[str, Any]) -> None:
    # Fail-safe: diagnostics must not affect runtime behavior.
    with contextlib.suppress(Exception):
        envelope = build_envelope(event=event, component="jobs", operation=operation, data=data)
        get_event_bus().publish(event, envelope)


class JobStore:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root if root is not None else jobs_root()

    @property
    def root(self) -> Path:
        return self._root

    def init_root(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    def job_dir(self, job_id: str) -> Path:
        return self._root / job_id

    def job_json_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "job.json"

    def job_log_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "job.log"

    def _counter_path(self) -> Path:
        return self._root / "counter.txt"

    def next_job_id(self) -> str:
        self.init_root()

        counter_path = self._counter_path()
        current = 0
        if counter_path.exists():
            raw = counter_path.read_text(encoding="utf-8").strip()
            if raw:
                current = int(raw)

        while True:
            current += 1
            # Persist counter first (atomic), then check for directory collision.
            _atomic_write_text(counter_path, f"{current}\n")
            job_id = f"job_{current:08d}"
            if not self.job_dir(job_id).exists():
                return job_id

    def _try_load_existing(self, job_id: str) -> Job | None:
        path = self.job_json_path(job_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Job.from_dict(data)
        except Exception:
            return None

    def save_job(self, job: Job) -> None:
        t0 = time.monotonic()
        self.init_root()
        jdir = self.job_dir(job.job_id)
        jdir.mkdir(parents=True, exist_ok=True)

        prev = self._try_load_existing(job.job_id)
        prev_state = prev.state if prev is not None else None
        prev_progress = prev.progress if prev is not None else None
        prev_error = prev.error if prev is not None else None

        payload = json.dumps(job.to_dict(), indent=2, sort_keys=True) + "\n"
        _atomic_write_text(self.job_json_path(job.job_id), payload)

        # Emit state update only on meaningful changes.
        state_changed = prev_state is None or prev_state != job.state
        progress_changed = prev_progress is None or prev_progress != job.progress
        error_changed = prev_error != job.error

        if state_changed or progress_changed:
            data: dict[str, Any] = {
                "job_id": job.job_id,
                "job_type": job.type.value,
                "state": job.state.value,
                "progress": job.progress,
                "status": "ok",
                "duration_ms": _duration_ms(t0, time.monotonic()),
            }
            if prev_state is not None:
                data["prev_state"] = prev_state.value
            _emit_diag("jobs.update_state", operation="jobs.update_state", data=data)
            _LOGGER.info(

                    f"job state updated: "
                    f"job_id={job.job_id} "
                    f"type={job.type.value} "
                    f"state={job.state.value} "
                    f"progress={job.progress:.3f}"

            )

        # Failure reason emission (best-effort, based on persisted fields).
        is_failed = job.state == JobState.FAILED
        became_failed = is_failed and (prev_state != JobState.FAILED)
        if is_failed and (became_failed or error_changed):
            err_msg = str(job.error or "")
            err_type = "unknown"
            if ":" in err_msg and err_msg.split(":", 1)[0].isidentifier():
                # Best-effort parsing for "ErrorType: message" patterns.
                err_type = err_msg.split(":", 1)[0]

            tb = ""
            # If caller stored traceback in meta (optional), use it.
            meta_tb = job.meta.get("traceback") or job.meta.get("error_traceback")
            if isinstance(meta_tb, str) and meta_tb.strip():
                tb = meta_tb
            elif "Traceback" in err_msg:
                tb = err_msg

            data = {
                "job_id": job.job_id,
                "job_type": job.type.value,
                "state": job.state.value,
                "progress": job.progress,
                "status": "failed",
                "duration_ms": _duration_ms(t0, time.monotonic()),
                "error_type": err_type,
                "error_message": _shorten_text(err_msg, max_chars=400),
                "traceback": _shorten_traceback(tb),
            }
            _emit_diag("jobs.fail", operation="jobs.fail", data=data)
            _LOGGER.error(

                    f"job failed: "
                    f"job_id={job.job_id} "
                    f"type={job.type.value} "
                    f"error_type={err_type} "
                    f"error_message={data['error_message']}"

            )

    def load_job(self, job_id: str) -> Job:
        path = self.job_json_path(job_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        return Job.from_dict(data)

    def list_job_ids(self) -> list[str]:
        if not self._root.exists():
            return []
        ids: list[str] = []
        for p in self._root.iterdir():
            if not p.is_dir():
                continue
            if (p / "job.json").exists():
                ids.append(p.name)
        return sorted(ids)

    def list_jobs(self) -> list[Job]:
        jobs = [self.load_job(jid) for jid in self.list_job_ids()]
        return jobs
