from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import AsyncIterator
from typing import TypeAlias

_EventItem: TypeAlias = tuple[int, str]
_QueueItem: TypeAlias = _EventItem | None


class JobEventBroker:
    """In-memory fan-out for live job events.

    The broker is fed by a single producer (event pump) and supports multiple
    SSE subscribers.

    Overflow policy is deterministic:
    - Per-subscriber queues are bounded.
    - On overflow, the oldest event is dropped and the new event is enqueued.

    Replay policy is deterministic:
    - A bounded recent-event buffer is retained.
    - Subscribers may request replay strictly after a persisted byte offset.
    """

    def __init__(
        self,
        *,
        max_queue_items: int = 2000,
        max_replay_items: int = 2000,
    ) -> None:
        self._max_queue_items = max(1, int(max_queue_items))
        self._max_replay_items = max(1, int(max_replay_items))
        self._mu = asyncio.Lock()
        self._subs: set[asyncio.Queue[_QueueItem]] = set()
        self._closed = False
        self._dropped_total = 0
        self._recent: deque[_EventItem] = deque(maxlen=self._max_replay_items)

    async def subscribe(self, *, after_offset: int = 0) -> AsyncIterator[str]:
        q: asyncio.Queue[_QueueItem] = asyncio.Queue(maxsize=self._max_queue_items)
        async with self._mu:
            replay = [item for item in self._recent if item[0] > after_offset]
            is_closed = self._closed
            if not is_closed:
                self._subs.add(q)

        try:
            for _, line in replay:
                yield line

            if is_closed:
                return

            while True:
                item = await q.get()
                if item is None:
                    return
                _, line = item
                yield line
        finally:
            async with self._mu:
                self._subs.discard(q)

    def publish(self, line: str, end_offset: int) -> None:
        if self._closed:
            return

        item = (int(end_offset), line)
        self._recent.append(item)
        for q in list(self._subs):
            try:
                q.put_nowait(item)
            except asyncio.QueueFull:
                self._dropped_total += 1
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()
                try:
                    q.put_nowait(item)
                except asyncio.QueueFull:
                    self._dropped_total += 1

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for q in list(self._subs):
            with contextlib.suppress(Exception):
                q.put_nowait(None)
        self._subs.clear()

    def dropped_total(self) -> int:
        return self._dropped_total
