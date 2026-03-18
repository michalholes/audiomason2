"""Detached process runtime launcher for PROCESS contract execution.

ASCII-only.
"""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from pathlib import Path


class ProcessContractRuntime:
    """Launch detached Core-owned authority processes for PROCESS contract jobs."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._children: list[int] = []

    def start(self, *, jobs_root: Path) -> None:
        self._spawn(jobs_root=jobs_root, adopt_all=True, job_id=None)

    def submit(self, *, job_id: str, jobs_root: Path) -> None:
        self._spawn(jobs_root=jobs_root, adopt_all=False, job_id=job_id)

    def shutdown(self) -> None:
        with self._lock:
            children = self._children[:]
            self._children.clear()
        for pid in children:
            self._terminate(pid, sig=signal.SIGTERM)
        for pid in children:
            self._reap_until_gone(pid)
        for pid in children:
            if self._is_alive(pid):
                self._terminate(pid, sig=signal.SIGKILL)
                self._reap_until_gone(pid)

    def _spawn(self, *, jobs_root: Path, adopt_all: bool, job_id: str | None) -> None:
        command = [sys.executable, "-m", "audiomason.core.process_contract_authority"]
        command.extend(["--jobs-root", str(jobs_root)])
        if adopt_all:
            command.append("--adopt-all")
        if job_id is not None:
            command.extend(["--job-id", job_id])

        env = dict(os.environ)
        src_root = Path(__file__).resolve().parents[2]
        repo_root = src_root.parent
        pythonpath = [str(repo_root), str(src_root)]
        existing = env.get("PYTHONPATH", "")
        if existing:
            pythonpath.append(existing)
        env["PYTHONPATH"] = os.pathsep.join(pythonpath)

        devnull_fd = os.open(os.devnull, os.O_RDWR)
        try:
            pid = os.posix_spawn(
                sys.executable,
                command,
                env,
                file_actions=(
                    (os.POSIX_SPAWN_DUP2, devnull_fd, 0),
                    (os.POSIX_SPAWN_DUP2, devnull_fd, 1),
                    (os.POSIX_SPAWN_DUP2, devnull_fd, 2),
                ),
                setsid=True,
            )
        finally:
            os.close(devnull_fd)

        with self._lock:
            self._children = [child for child in self._children if self._refresh_child(child)]
            self._children.append(pid)

    def _refresh_child(self, pid: int) -> bool:
        self._reap_child(pid)
        return self._is_alive(pid)

    def _reap_child(self, pid: int) -> None:
        with OSErrorGuard():
            os.waitpid(pid, os.WNOHANG)

    def _reap_until_gone(self, pid: int) -> None:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            try:
                waited_pid, _status = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                return
            except OSError:
                return
            if waited_pid != 0:
                return
            if not self._is_alive(pid):
                return
            time.sleep(0.02)

    def _terminate(self, pid: int, *, sig: signal.Signals) -> None:
        with OSErrorGuard():
            os.killpg(pid, sig)

    def _is_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True


class OSErrorGuard:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        return exc_type is not None and issubclass(exc_type, OSError)


_RUNTIME = ProcessContractRuntime()


def get_process_contract_runtime() -> ProcessContractRuntime:
    return _RUNTIME


def reset_process_contract_runtime_for_tests() -> None:
    _RUNTIME.shutdown()


__all__ = [
    "ProcessContractRuntime",
    "get_process_contract_runtime",
    "reset_process_contract_runtime_for_tests",
]
