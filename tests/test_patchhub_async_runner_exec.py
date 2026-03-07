# ruff: noqa: E402
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from patchhub.asgi.async_runner_exec import AsyncRunnerExecutor


class _HangingStdout:
    async def readline(self) -> bytes:
        await asyncio.sleep(3600)
        return b""


class _FakeProcess:
    def __init__(self) -> None:
        self.stdout = _HangingStdout()
        self.returncode: int | None = None
        self.pid = 1234

    async def wait(self) -> int:
        self.returncode = 0
        return 0


class TestPatchhubAsyncRunnerExec(unittest.IsolatedAsyncioTestCase):
    async def test_run_times_out_hanging_stdout_tail_after_exit(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            log_path = root / "runner.log"
            proc = _FakeProcess()
            executor = AsyncRunnerExecutor()
            with patch(
                "patchhub.asgi.async_runner_exec.asyncio.create_subprocess_exec",
                return_value=proc,
            ):
                result = await executor.run(
                    ["python3", "scripts/am_patch.py", "500"],
                    cwd=root,
                    log_path=log_path,
                    post_exit_grace_s=1,
                )

            self.assertEqual(result.return_code, 0)
            self.assertTrue(result.stdout_tail_timed_out)
            self.assertEqual(log_path.read_text(encoding="utf-8"), "")
