from __future__ import annotations

import json
import threading
import time
from collections import deque
from collections.abc import Iterator

from audiomason.core.events import get_event_bus

_MAX_EVENTS = 2000

_lock = threading.Lock()
_cond = threading.Condition(_lock)
_events: deque[tuple[int, str]] = deque(maxlen=_MAX_EVENTS)
_next_id = 1
_installed = False


def install_event_tap() -> None:
    """Install a global EventBus subscriber that stores recent diagnostics.

    This is installed once per process to avoid per-connection subscriptions.
    """
    global _installed
    if _installed:
        return

    def _on_any(event: str, data: dict[str, object]) -> None:
        try:
            payload_obj: dict[str, object] = {
                "event": str(event),
                "data": dict(data),
            }
            payload = json.dumps(
                payload_obj,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
        except Exception:
            return

        global _next_id
        with _cond:
            eid = _next_id
            _next_id += 1
            _events.append((eid, payload))
            _cond.notify_all()

    get_event_bus().subscribe_all(_on_any)
    _installed = True


def snapshot(*, since_id: int = 0, limit: int = 200) -> list[tuple[int, str]]:
    """Return up to `limit` events with id > since_id."""
    if limit <= 0:
        limit = 1
    if limit > 2000:
        limit = 2000

    with _lock:
        items = [(eid, payload) for (eid, payload) in _events if eid > since_id]
    if len(items) > limit:
        items = items[-limit:]
    return items


def stream(*, since_id: int = 0, heartbeat_s: float = 15.0) -> Iterator[tuple[int | None, str]]:
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
        with _cond:
            _cond.wait(timeout=max(0.1, float(heartbeat_s)))

        # Heartbeat to keep SSE alive. Do not emit an SSE id for heartbeat.
        now = time.time()
        heartbeat: dict[str, object] = {
            "event": "heartbeat",
            "data": {"ts": now},
        }
        yield (
            None,
            json.dumps(
                heartbeat,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
