from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from patchhub.asgi.job_event_broker import JobEventBroker  # noqa: E402
from patchhub.asgi.job_events_live_source import stream_job_events_live_source  # noqa: E402


class TestPatchhubLiveEventsSource(unittest.IsolatedAsyncioTestCase):
    async def test_active_job_waits_for_broker_and_switches_to_live(self) -> None:
        with TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "job.jsonl"
            jsonl_path.write_text(
                '{"type":"log","msg":"queued"}\n',
                encoding="utf-8",
            )
            status = {"value": "queued"}
            broker_ref: dict[str, JobEventBroker | None] = {"value": None}

            async def job_status() -> str | None:
                return str(status["value"])

            async def get_broker() -> JobEventBroker | None:
                return broker_ref["value"]

            async def historical_stream():
                raise AssertionError("historical fallback must not run for active jobs")
                yield b""

            async def publish_live() -> None:
                await asyncio.sleep(0.05)
                broker = JobEventBroker()
                broker_ref["value"] = broker
                await asyncio.sleep(0.05)
                broker.publish('{"type":"log","msg":"live"}')
                await asyncio.sleep(0.01)
                status["value"] = "success"
                broker.close()

            task = asyncio.create_task(publish_live())
            chunks: list[bytes] = []
            async for chunk in stream_job_events_live_source(
                job_id="job-500-live",
                jsonl_path=jsonl_path,
                in_memory_job=True,
                job_status=job_status,
                get_broker=get_broker,
                historical_stream=historical_stream,
                broker_poll_interval_s=0.01,
            ):
                chunks.append(chunk)
            await task

        payload = b"".join(chunks).decode("utf-8")
        self.assertIn('data: {"type":"log","msg":"queued"}', payload)
        self.assertIn('data: {"type":"log","msg":"live"}', payload)
        self.assertIn("event: end", payload)
        self.assertIn('"status": "success"', payload)

    async def test_disk_only_job_uses_historical_stream(self) -> None:
        with TemporaryDirectory() as tmpdir:
            jsonl_path = Path(tmpdir) / "job.jsonl"
            jsonl_path.write_text("", encoding="utf-8")
            seen: list[str] = []

            async def job_status() -> str | None:
                return "success"

            async def get_broker() -> JobEventBroker | None:
                raise AssertionError("disk-only jobs must not query live broker")

            async def historical_stream():
                seen.append("historical")
                yield b'data: {"type":"log","msg":"from_history"}\n\n'
                yield b'event: end\ndata: {"reason": "job_completed"}\n\n'

            chunks = [
                chunk
                async for chunk in stream_job_events_live_source(
                    job_id="job-500-history",
                    jsonl_path=jsonl_path,
                    in_memory_job=False,
                    job_status=job_status,
                    get_broker=get_broker,
                    historical_stream=historical_stream,
                )
            ]

        self.assertEqual(seen, ["historical"])
        payload = b"".join(chunks).decode("utf-8")
        self.assertIn("from_history", payload)
        self.assertIn("event: end", payload)
