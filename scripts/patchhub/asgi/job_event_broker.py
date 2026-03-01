from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator


class JobEventBroker:
    """In-memory fan-out for live job events.

    The broker is fed by a single producer (event pump) and supports multiple
    SSE subscribers.

    Overflow policy is deterministic:
    - Per-subscriber queues are bounded.
    - On overflow, the oldest event is dropped and the new event is enqueued.
    """

    def __init__(self, *, max_queue_items: int = 2000) -> None:
        self._max_queue_items = max(1, int(max_queue_items))
        self._mu = asyncio.Lock()
        self._subs: set[asyncio.Queue[str | None]] = set()
        self._closed = False
        self._dropped_total = 0

    async def subscribe(self) -> AsyncIterator[str]:
        q: asyncio.Queue[str | None] = asyncio.Queue(maxsize=self._max_queue_items)
        async with self._mu:
            if self._closed:
                return
            self._subs.add(q)

        try:
            while True:
                item = await q.get()
                if item is None:
                    return
                yield item
        finally:
            async with self._mu:
                self._subs.discard(q)

    def publish(self, line: str) -> None:
        if self._closed:
            return

        for q in list(self._subs):
            try:
                q.put_nowait(line)
            except asyncio.QueueFull:
                self._dropped_total += 1
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()
                try:
                    q.put_nowait(line)
                except asyncio.QueueFull:
                    # If still full, give up for this subscriber.
                    self._dropped_total += 1

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        # Deterministic termination: never drop the termination sentinel.
        # Backpressure may drop data lines, but close MUST end subscriber loops.
        for q in list(self._subs):
            while True:
                try:
                    q.put_nowait(None)
                    break
                except asyncio.QueueFull:
                    with contextlib.suppress(Exception):
                        q.get_nowait()

        self._subs.clear()

    def dropped_total(self) -> int:
        return self._dropped_total
