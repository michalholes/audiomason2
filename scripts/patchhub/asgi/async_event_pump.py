from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from pathlib import Path


async def _connect_and_stream(
    socket_path: str,
    jsonl_path: Path,
    publish: Callable[[str], None] | None,
) -> None:
    reader, writer = await asyncio.open_unix_connection(socket_path)
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    f = jsonl_path.open("a", encoding="utf-8")
    try:
        flush_every = 20
        n = 0
        while True:
            raw = await reader.readline()
            if not raw:
                return
            try:
                line = raw.decode("utf-8")
            except Exception:
                line = raw.decode("utf-8", errors="replace")

            line = line.rstrip("\n")
            if not line.strip():
                continue

            if publish is not None:
                publish(line)

            f.write(line + "\n")
            n += 1
            if n >= flush_every:
                f.flush()
                n = 0
    finally:
        with contextlib.suppress(Exception):
            f.flush()
        with contextlib.suppress(Exception):
            f.close()
        with contextlib.suppress(Exception):
            writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()


async def start_event_pump(
    *,
    socket_path: str,
    jsonl_path: Path,
    publish: Callable[[str], None] | None = None,
    connect_timeout_s: float = 10.0,
    retry_sleep_s: float = 0.25,
) -> None:
    """Start an async event pump that persists runner IPC events to a JSONL file.

    If publish is provided, each non-empty line is also forwarded immediately.
    The function returns when the stream ends or when connect timeout elapses.
    """

    deadline = asyncio.get_running_loop().time() + max(connect_timeout_s, 0.0)
    while True:
        try:
            await _connect_and_stream(socket_path, jsonl_path, publish)
            return
        except FileNotFoundError:
            pass
        except ConnectionRefusedError:
            pass
        except OSError:
            pass

        if connect_timeout_s <= 0:
            return
        if asyncio.get_running_loop().time() >= deadline:
            return
        await asyncio.sleep(retry_sleep_s)
