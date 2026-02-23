from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path


async def _connect_and_stream(socket_path: str, jsonl_path: Path) -> None:
    reader, _writer = await asyncio.open_unix_connection(socket_path)
    try:
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with jsonl_path.open("a", encoding="utf-8") as f:
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
                f.write(line + "\n")
                f.flush()
    finally:
        # The writer will be closed automatically when GC'd; close explicitly.
        with contextlib.suppress(Exception):
            _writer.close()


async def start_event_pump(
    *,
    socket_path: str,
    jsonl_path: Path,
    connect_timeout_s: float = 10.0,
    retry_sleep_s: float = 0.25,
) -> None:
    """Start an async event pump that appends runner IPC events to a JSONL file.

    The function returns when the stream ends or when connect timeout elapses.
    """

    deadline = asyncio.get_running_loop().time() + max(connect_timeout_s, 0.0)
    while True:
        try:
            await _connect_and_stream(socket_path, jsonl_path)
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
