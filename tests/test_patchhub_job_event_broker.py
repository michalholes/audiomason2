# ruff: noqa: E402
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from patchhub.asgi.job_event_broker import JobEventBroker


class TestPatchhubJobEventBroker(unittest.IsolatedAsyncioTestCase):
    async def test_subscribe_replays_after_offset_then_continues_live(self) -> None:
        broker = JobEventBroker(max_replay_items=8)
        broker.publish('{"type":"log","msg":"same"}', 10)
        broker.publish('{"type":"log","msg":"same"}', 20)

        sub = broker.subscribe(after_offset=10).__aiter__()
        first = await asyncio.wait_for(sub.__anext__(), timeout=0.1)
        broker.publish('{"type":"log","msg":"next"}', 30)
        second = await asyncio.wait_for(sub.__anext__(), timeout=0.1)
        await sub.aclose()

        self.assertEqual(first, '{"type":"log","msg":"same"}')
        self.assertEqual(second, '{"type":"log","msg":"next"}')

    async def test_close_keeps_termination_signal_when_queue_is_full(self) -> None:
        broker = JobEventBroker(max_queue_items=1, max_replay_items=8)
        q: asyncio.Queue[object] = asyncio.Queue(maxsize=1)
        q.put_nowait((10, '{"type":"log","msg":"stale"}'))
        broker._subs.add(q)

        broker.close()

        self.assertIsNone(q.get_nowait())
        self.assertEqual(broker.dropped_total(), 1)
