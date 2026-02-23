from __future__ import annotations

import contextlib
import threading
from pathlib import Path

from .events_socket import iter_socket_lines


class EventPumpRegistry:
    def __init__(self) -> None:
        self._mu = threading.Lock()
        self._active: set[str] = set()

    def start(self, job_id: str, socket_path: str, jsonl_path: Path) -> None:
        job_id = str(job_id)
        if not job_id:
            return

        with self._mu:
            if job_id in self._active:
                return
            self._active.add(job_id)

        t = threading.Thread(
            target=self._run,
            args=(job_id, socket_path, jsonl_path),
            name="patchhub_event_pump_" + job_id,
            daemon=True,
        )
        t.start()

    def _run(self, job_id: str, socket_path: str, jsonl_path: Path) -> None:
        try:
            jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            with jsonl_path.open("ab") as fp:
                for line in iter_socket_lines(
                    socket_path,
                    connect_timeout_s=60.0,
                    retry_sleep_s=0.2,
                ):
                    data = line
                    if not data.endswith("\n"):
                        data += "\n"
                    fp.write(data.encode("utf-8", errors="replace"))
                    fp.flush()
        finally:
            with self._mu:
                self._active.discard(job_id)


_REGISTRY = EventPumpRegistry()


def start_event_pump(job_id: str, socket_path: str, jsonl_path: Path) -> None:
    """Start a single socket->jsonl pump for job_id.

    The pump is best-effort and must not raise.
    """

    with contextlib.suppress(Exception):
        _REGISTRY.start(job_id, socket_path, jsonl_path)
