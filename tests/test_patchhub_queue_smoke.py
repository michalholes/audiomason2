# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import tempfile
import time
import unittest
from pathlib import Path

from patchhub.models import JobRecord
from patchhub.queue import JobQueue, utc_now


class FakeExec:
    def __init__(self) -> None:
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def terminate(self) -> bool:
        return False

    def run(self, argv: list[str], cwd: Path, log_path: Path, on_line=None):
        self._running = True
        log_path.write_text("RESULT: SUCCESS\n", encoding="utf-8")
        self._running = False
        return type("R", (), {"return_code": 0})()


class TestQueueSmoke(unittest.TestCase):
    def test_enqueue_and_persist(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            patches = repo_root / "patches"
            patches.mkdir()
            jobs_root = patches / "artifacts" / "web_jobs"
            lock_path = patches / "am_patch.lock"

            q = JobQueue(
                repo_root=repo_root, lock_path=lock_path, jobs_root=jobs_root, executor=FakeExec()
            )
            try:
                job = JobRecord(
                    job_id="abc",
                    created_utc=utc_now(),
                    mode="patch",
                    issue_id="1",
                    commit_message="m",
                    patch_path="p",
                    raw_command="",
                    canonical_command=["true"],
                )
                q.enqueue(job)
                time.sleep(0.5)
                self.assertTrue((jobs_root / "abc" / "job.json").exists())
            finally:
                q.stop()
