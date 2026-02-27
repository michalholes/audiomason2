from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Callable
from pathlib import Path

_CHUNK_BYTES = 8192
_MAX_LINE_BYTES = 64 * 1024 * 1024


def _oversize_notice(*, dropped_bytes: int) -> str:
    payload = {
        "type": "patchhub_notice",
        "code": "IPC_LINE_TOO_LARGE_DROPPED",
        "dropped_bytes": dropped_bytes,
    }
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def _write_line(
    *,
    f,
    line: str,
    publish: Callable[[str], None] | None,
) -> None:
    line = line.rstrip("\n")
    if not line.strip():
        return

    if publish is not None:
        publish(line)

    f.write(line + "\n")


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
        buf = b""
        while True:
            chunk = await reader.read(_CHUNK_BYTES)
            if not chunk:
                if buf.strip():
                    line = buf.decode("utf-8", errors="replace")
                    _write_line(f=f, line=line, publish=publish)
                return

            buf += chunk
            while True:
                nl = buf.find(b"\n")
                if nl < 0:
                    break

                line_bytes = buf[:nl]
                buf = buf[nl + 1 :]

                if not line_bytes.strip():
                    continue

                line = line_bytes.decode("utf-8", errors="replace")
                _write_line(f=f, line=line, publish=publish)
                n += 1
                if n >= flush_every:
                    f.flush()
                    n = 0

            if len(buf) > _MAX_LINE_BYTES:
                dropped = len(buf)
                buf = b""
                notice = _oversize_notice(dropped_bytes=dropped)
                _write_line(f=f, line=notice, publish=publish)
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
