from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExecResult:
    return_code: int


class RunnerExecutor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[str] | None = None

    def is_running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def terminate(self) -> bool:
        with self._lock:
            proc = self._proc
        if proc is None:
            return False
        if proc.poll() is not None:
            return False
        try:
            proc.terminate()
        except Exception:
            return False
        return True

    def run(
        self,
        argv: list[str],
        cwd: Path,
        log_path: Path,
        on_line: Callable[[str], None] | None = None,
    ) -> ExecResult:
        log_path.parent.mkdir(parents=True, exist_ok=True)

        proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        with self._lock:
            self._proc = proc

        try:
            with log_path.open("w", encoding="utf-8") as f:
                assert proc.stdout is not None
                for line in proc.stdout:
                    f.write(line)
                    f.flush()
                    if on_line is not None:
                        on_line(line)
            rc = proc.wait()
            return ExecResult(return_code=int(rc))
        finally:
            with self._lock:
                self._proc = None
