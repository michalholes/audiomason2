# ruff: noqa: E402
from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import patchhub.asgi.async_queue as async_queue_mod
from patchhub.models import JobRecord


class _FakeExecutor:
    async def is_running(self) -> bool:
        return False

    async def terminate(self) -> bool:
        return False

    async def run(self, argv: list[str], cwd: Path, log_path: Path):
        del argv, cwd
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("runner\n", encoding="utf-8")
        return type("ExecResult", (), {"return_code": 0})()


class TestPatchhubAsyncQueueCompletion(unittest.IsolatedAsyncioTestCase):
    async def test_runner_completion_waits_for_pump_tail_before_finalizing(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo_root = root / "repo"
            jobs_root = root / "jobs"
            repo_root.mkdir()
            jobs_root.mkdir()
            queue = async_queue_mod.AsyncJobQueue(
                repo_root=repo_root,
                lock_path=root / "am_patch.lock",
                jobs_root=jobs_root,
                executor=_FakeExecutor(),
            )
            job = JobRecord(
                job_id="job-504-tail",
                created_utc="2026-03-06T00:00:00Z",
                mode="patch",
                issue_id="504",
                commit_summary="Fix PatchHub completion sequencing",
                patch_basename="issue_504.zip",
                raw_command=(
                    "python3 scripts/am_patch.py 504 "
                    '"Fix PatchHub completion sequencing" '
                    "patches/issue_504.zip"
                ),
                canonical_command=["python3", "scripts/am_patch.py", "504"],
            )

            async def fake_start_event_pump(
                *,
                socket_path: str,
                jsonl_path: Path,
                publish=None,
                connect_timeout_s: float = 10.0,
                retry_sleep_s: float = 0.25,
            ) -> None:
                del socket_path, connect_timeout_s, retry_sleep_s
                await asyncio.sleep(0.02)
                line = '{"type":"log","msg":"tail"}'
                with jsonl_path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
                    end_offset = f.tell()
                if publish is not None:
                    publish(line, end_offset)

            async def wait_for_success() -> async_queue_mod.JobRecord:
                deadline = asyncio.get_running_loop().time() + 2.0
                while True:
                    current = await queue.get_job(job.job_id)
                    if current is not None and current.status == "success":
                        return current
                    if asyncio.get_running_loop().time() >= deadline:
                        raise AssertionError("job did not finish")
                    await asyncio.sleep(0.01)

            with (
                patch.object(
                    async_queue_mod,
                    "start_event_pump",
                    side_effect=fake_start_event_pump,
                ),
                patch.object(
                    async_queue_mod,
                    "job_socket_path",
                    return_value=str(root / "job-504-tail.sock"),
                ),
            ):
                await queue.start()
                try:
                    await queue.enqueue(job)
                    finished = await wait_for_success()
                finally:
                    with contextlib.suppress(asyncio.CancelledError):
                        await queue.stop()

            self.assertEqual(finished.return_code, 0)
            jsonl_path = jobs_root / job.job_id / "am_patch_issue_504.jsonl"
            jsonl_lines = jsonl_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(jsonl_lines[-1], '{"type":"log","msg":"tail"}')
            job_json = json.loads((jobs_root / job.job_id / "job.json").read_text())
            self.assertEqual(job_json["status"], "success")
