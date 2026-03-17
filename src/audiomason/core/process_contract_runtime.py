"""Detached Core-owned runtime for PROCESS contract execution.

ASCII-only.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Coroutine
from typing import Any

_ProcessCoroutineFactory = Callable[[], Coroutine[Any, Any, None]]


class ProcessContractRuntime:
    """Own a detached event loop for durable PROCESS contract execution."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._submitted: set[str] = set()

    def start(self) -> None:
        with self._lock:
            thread = self._thread
            if thread is not None and thread.is_alive():
                return
            self._ready.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="audiomason-process-contract-runtime",
                daemon=True,
            )
            self._thread.start()
        self._ready.wait(timeout=5.0)
        if not self._ready.is_set():
            raise RuntimeError("process contract runtime failed to start")

    def submit(self, job_id: str, factory: _ProcessCoroutineFactory) -> bool:
        self.start()
        with self._lock:
            loop = self._loop
            if loop is None or not loop.is_running():
                raise RuntimeError("process contract runtime loop is unavailable")
            if job_id in self._submitted:
                return False
            self._submitted.add(job_id)
        try:
            loop.call_soon_threadsafe(self._create_task, job_id, factory)
        except Exception:
            self._release(job_id)
            raise
        return True

    def shutdown(self) -> None:
        with self._lock:
            loop = self._loop
            thread = self._thread
        if loop is not None:
            loop.call_soon_threadsafe(loop.stop)
        if thread is not None:
            thread.join(timeout=2.0)
        with self._lock:
            self._loop = None
            self._thread = None
            self._submitted.clear()
            self._ready.clear()

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with self._lock:
            self._loop = loop
        self._ready.set()
        try:
            loop.run_forever()
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            with self._lock:
                self._loop = None
                self._thread = None
                self._submitted.clear()
            asyncio.set_event_loop(None)
            loop.close()

    def _create_task(self, job_id: str, factory: _ProcessCoroutineFactory) -> None:
        try:
            task = asyncio.create_task(factory())
        except Exception:
            self._release(job_id)
            raise
        task.add_done_callback(lambda _task: self._release(job_id))

    def _release(self, job_id: str) -> None:
        with self._lock:
            self._submitted.discard(job_id)


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
