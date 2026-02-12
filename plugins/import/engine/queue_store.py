"""Import engine queue persistence.

Stored under the file_io JOBS root.

ASCII-only.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, cast

from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

from .types import ImportQueueState, QueueMode

_ALLOWED_MODES = {"paused", "running"}

_BASE_DIR = "import/engine"
_QUEUE_PATH = f"{_BASE_DIR}/queue.json"


def _emit_diag(event: str, *, operation: str, data: dict[str, Any]) -> None:
    try:
        env = build_envelope(
            event=event,
            component="import.engine.queue_store",
            operation=operation,
            data=data,
        )
        get_event_bus().publish(event, env)
    except Exception:
        return


class ImportQueueStore:
    def __init__(self, fs: FileService) -> None:
        self._fs = fs
        if not self._fs.exists(RootName.JOBS, _BASE_DIR):
            self._fs.mkdir(RootName.JOBS, _BASE_DIR, parents=True, exist_ok=True)

    def load(self) -> ImportQueueState:
        _emit_diag("boundary.start", operation="load", data={})
        if not self._fs.exists(RootName.JOBS, _QUEUE_PATH):
            state = ImportQueueState()
            self.save(state)
            _emit_diag("boundary.end", operation="load", data={"status": "succeeded"})
            return state

        with self._fs.open_read(RootName.JOBS, _QUEUE_PATH) as f:
            raw = f.read().decode("utf-8")
        obj = json.loads(raw)

        mode_val = obj.get("mode", "running")
        mode = str(mode_val) if mode_val is not None else "running"
        if mode not in _ALLOWED_MODES:
            mode = "running"

        state = ImportQueueState(mode=cast(QueueMode, mode))
        _emit_diag("boundary.end", operation="load", data={"status": "succeeded"})
        return state

    def save(self, state: ImportQueueState) -> None:
        _emit_diag("boundary.start", operation="save", data={"mode": state.mode})
        payload = json.dumps(asdict(state), indent=2, sort_keys=True) + "\n"
        with self._fs.open_write(
            RootName.JOBS, _QUEUE_PATH, overwrite=True, mkdir_parents=True
        ) as f:
            f.write(payload.encode("utf-8"))
        _emit_diag(
            "boundary.end", operation="save", data={"status": "succeeded", "mode": state.mode}
        )
