from __future__ import annotations

import json
from pathlib import Path

from audiomason.core.jobs.model import Job
from audiomason.core.jobs.paths import jobs_root


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


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

    def save_job(self, job: Job) -> None:
        self.init_root()
        jdir = self.job_dir(job.job_id)
        jdir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(job.to_dict(), indent=2, sort_keys=True) + "\n"
        _atomic_write_text(self.job_json_path(job.job_id), payload)

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
