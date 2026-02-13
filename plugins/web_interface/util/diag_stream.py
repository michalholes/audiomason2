from __future__ import annotations

import json
import threading
import time
from collections import deque
from collections.abc import Iterator
from typing import Any

from audiomason.core.events import get_event_bus

_MAX_EVENTS = 2000

_LOCK = threading.Lock()
_COND = threading.Condition(_LOCK)
_EVENTS: deque[tuple[int, str]] = deque(maxlen=_MAX_EVENTS)
_NEXT_ID = 1
_INSTALLED = False


def install_event_tap() -> None:
    """Install a global EventBus subscriber that stores recent diagnostics.

    This is installed once per process to avoid per-connection subscriptions.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    def _on_any(event: str, data: dict[str, Any]) -> None:
        try:
            payload = json.dumps(
                {"event": event, "data": data},
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
        except Exception:
            return

        global _NEXT_ID
        with _COND:
            eid = _NEXT_ID
            _NEXT_ID += 1
            _EVENTS.append((eid, payload))
            _COND.notify_all()

    get_event_bus().subscribe_all(_on_any)
    _INSTALLED = True


def snapshot(*, since_id: int = 0, limit: int = 200) -> list[tuple[int, str]]:
    """Return up to `limit` events with id > since_id."""
    if limit <= 0:
        limit = 1
    if limit > 2000:
        limit = 2000

    with _LOCK:
        items = [(eid, payload) for (eid, payload) in _EVENTS if eid > since_id]
    if len(items) > limit:
        items = items[-limit:]
    return items


def stream(*, since_id: int = 0, heartbeat_s: float = 15.0) -> Iterator[tuple[int, str]]:
    """Yield (id, payload) tuples from the ring buffer, blocking for new items."""
    last = since_id
    while True:
        items = snapshot(since_id=last, limit=500)
        if items:
            for eid, payload in items:
                last = eid
                yield (eid, payload)
            continue

        # Wait for new items (or heartbeat).
        with _COND:
            _COND.wait(timeout=max(0.1, float(heartbeat_s)))

        # Heartbeat to keep SSE alive.
        now = time.time()
        yield (
            last,
            json.dumps(
                {"event": "heartbeat", "data": {"ts": now}}, separators=(",", ":"), sort_keys=True
            ),
        )
