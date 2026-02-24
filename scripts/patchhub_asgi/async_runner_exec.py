from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path


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

    async def run(self, argv: list[str], cwd: Path, log_path: Path) -> ExecResult:
        await asyncio.to_thread(_truncate_file_sync, log_path)

        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        async with self._lock:
            self._proc = proc

        try:
            assert proc.stdout is not None
            while True:
                raw = await proc.stdout.readline()
                if not raw:
                    break
                try:
                    line = raw.decode("utf-8")
                except Exception:
                    line = raw.decode("utf-8", errors="replace")
                await asyncio.to_thread(_append_text_sync, log_path, line)

            rc = await proc.wait()
            return ExecResult(return_code=int(rc))
        finally:
            async with self._lock:
                self._proc = None
