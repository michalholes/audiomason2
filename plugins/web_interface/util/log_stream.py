from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Iterator

from audiomason.core.log_bus import LogRecord, get_log_bus

_MAX_RECORDS = 2000

_lock = threading.Lock()
_cond = threading.Condition(_lock)
_records: deque[tuple[int, str]] = deque(maxlen=_MAX_RECORDS)
_next_id = 1
_installed = False


def install_log_tap() -> None:
    """Install a global LogBus subscriber that stores recent log lines.

    This is installed once per process to avoid per-connection subscriptions.
    """

    global _installed
    if _installed:
        return

    def _on_any(record: LogRecord) -> None:
        # Store a single line per record. UI adds its own newline.
        line = (record.plain or "").rstrip("\n")

        global _next_id
        with _cond:
            eid = _next_id
            _next_id += 1
            _records.append((eid, line))
            _cond.notify_all()

    get_log_bus().subscribe_all(_on_any)
    _installed = True


def snapshot(*, since_id: int = 0, limit: int = 200) -> list[tuple[int, str]]:
    """Return up to `limit` log records with id > since_id."""

    if limit <= 0:
        limit = 1
    if limit > 2000:
        limit = 2000

    with _lock:
        items = [(eid, line) for (eid, line) in _records if eid > since_id]
    if len(items) > limit:
        items = items[-limit:]
    return items


def tail_text(*, lines: int = 200) -> str:
    """Return last `lines` records as one string (newline-terminated)."""

    n = int(lines)
    if n <= 0:
        n = 1
    if n > 2000:
        n = 2000

    with _lock:
        items = list(_records)[-n:]

    txt = "\n".join(line for _eid, line in items)
    return txt + ("\n" if txt else "")


def stream(*, since_id: int = 0, heartbeat_s: float = 15.0) -> Iterator[tuple[int | None, str]]:
    """Yield (id, line) tuples from the ring buffer, blocking for new items."""

    last = since_id
    while True:
        items = snapshot(since_id=last, limit=500)
        if items:
            for eid, line in items:
                last = eid
                yield (eid, line)
            continue

        with _cond:
            _cond.wait(timeout=max(0.1, float(heartbeat_s)))

        # Heartbeat to keep SSE alive. Do not emit an SSE id for heartbeat.
        yield (None, f"heartbeat {time.time()}")
