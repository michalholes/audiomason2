from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

from patchhub.app_support import read_tail

from .job_event_broker import JobEventBroker


async def stream_job_events_live_source(
    *,
    job_id: str,
    jsonl_path: Path,
    in_memory_job: bool,
    job_status: Callable[[], Awaitable[str | None]],
    get_broker: Callable[[], Awaitable[JobEventBroker | None]],
    historical_stream: Callable[[], AsyncIterator[bytes]],
    tail_lines: int = 500,
    ping_interval_s: float = 10.0,
    broker_poll_interval_s: float = 0.1,
) -> AsyncIterator[bytes]:
    if not in_memory_job:
        async for chunk in historical_stream():
            yield chunk
        return

    tail = await asyncio.to_thread(read_tail, jsonl_path, tail_lines)
    if tail:
        for line in tail.splitlines():
            if not line.strip():
                continue
            yield f"data: {line}\n\n".encode()

    last_ping = asyncio.get_running_loop().time()
    while True:
        broker = await get_broker()
        if broker is not None:
            break

        status = await job_status()
        if status is None:
            data = json.dumps({"reason": "job_not_found"}, ensure_ascii=True)
            yield f"event: end\ndata: {data}\n\n".encode()
            return

        if status not in ("queued", "running"):
            data = json.dumps(
                {"reason": "job_completed", "status": str(status)},
                ensure_ascii=True,
            )
            yield f"event: end\ndata: {data}\n\n".encode()
            return

        now = asyncio.get_running_loop().time()
        if now - last_ping >= ping_interval_s:
            yield b": ping\n\n"
            last_ping = now

        await asyncio.sleep(broker_poll_interval_s)

    sub = broker.subscribe().__aiter__()
    while True:
        try:
            line = await asyncio.wait_for(sub.__anext__(), timeout=10.0)
        except TimeoutError:
            yield b": ping\n\n"
            continue
        except StopAsyncIteration:
            break
        yield f"data: {line}\n\n".encode()

    status = await job_status()
    data = json.dumps(
        {"reason": "job_completed", "status": status or ""},
        ensure_ascii=True,
    )
    yield f"event: end\ndata: {data}\n\n".encode()
