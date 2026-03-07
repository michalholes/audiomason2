from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from .async_task_grace import wait_with_grace


def _truncate_file_sync(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def _append_text_sync(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(text)


@dataclass(frozen=True)
class ExecResult:
    return_code: int
    stdout_tail_timed_out: bool = False


class AsyncRunnerExecutor:
    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()

    async def is_running(self) -> bool:
        async with self._lock:
            proc = self._proc
        return proc is not None and proc.returncode is None

    async def terminate(self) -> bool:
        async with self._lock:
            proc = self._proc
        if proc is None or proc.returncode is not None:
            return False
        try:
            proc.terminate()
        except ProcessLookupError:
            return False
        except Exception:
            return False
        return True

    async def _drain_stdout(
        self,
        stdout: asyncio.StreamReader,
        *,
        log_path: Path,
    ) -> None:
        while True:
            raw = await stdout.readline()
            if not raw:
                return
            try:
                line = raw.decode("utf-8")
            except Exception:
                line = raw.decode("utf-8", errors="replace")
            await asyncio.to_thread(_append_text_sync, log_path, line)

    async def run(
        self,
        argv: list[str],
        cwd: Path,
        log_path: Path,
        *,
        post_exit_grace_s: int = 5,
    ) -> ExecResult:
        await asyncio.to_thread(_truncate_file_sync, log_path)

        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        async with self._lock:
            self._proc = proc

        reader_task: asyncio.Task[object] | None = None
        try:
            assert proc.stdout is not None
            reader_task = asyncio.create_task(
                self._drain_stdout(proc.stdout, log_path=log_path),
                name=f"patchhub_runner_stdout_{proc.pid}",
            )
            rc = await proc.wait()
            timed_out = await wait_with_grace(reader_task, grace_s=post_exit_grace_s)
            return ExecResult(
                return_code=int(rc),
                stdout_tail_timed_out=timed_out,
            )
        finally:
            async with self._lock:
                self._proc = None
