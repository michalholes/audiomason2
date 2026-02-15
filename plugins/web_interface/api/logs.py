from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from audiomason.core.config import ConfigResolver
from audiomason.core.diagnostics import is_diagnostics_enabled
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

from ..util.diag_stream import snapshot, stream
from ..util.log_stream import install_log_tap
from ..util.log_stream import stream as logbus_iter
from ..util.log_stream import tail_text as logbus_tail_text

DIAGNOSTICS_REL_PATH = "diagnostics/diagnostics.jsonl"


def _get_resolver(request: Request) -> ConfigResolver:
    resolver = getattr(request.app.state, "config_resolver", None)
    if isinstance(resolver, ConfigResolver):
        return resolver
    return ConfigResolver()


def _get_file_service(resolver: ConfigResolver) -> FileService | None:
    try:
        return FileService.from_resolver(resolver)
    except Exception:
        return None


def _tail_jsonl(fs: FileService, lines: int) -> str:
    # Tail a JSONL file without reading it fully into memory.
    # All filesystem access is routed via the file_io capability.
    n = max(0, int(lines))
    if n <= 0:
        return ""

    try:
        with fs.open_read(root=RootName.STAGE, rel_path=DIAGNOSTICS_REL_PATH) as f:
            try:
                f.seek(0, 2)
                end = int(f.tell())
            except Exception:
                # Non-seekable stream: fall back to reading linearly.
                end = -1

            if end >= 0:
                # Read backwards in chunks until we have enough newlines.
                chunk_size = 8192
                pos = end
                buf = bytearray()
                newlines = 0

                while pos > 0 and newlines <= n:
                    read_size = chunk_size if pos >= chunk_size else pos
                    pos -= read_size
                    f.seek(pos)
                    chunk = f.read(read_size)
                    if not chunk:
                        break
                    buf[:0] = chunk
                    newlines = buf.count(b"\n")
                    # Cap memory usage.
                    if len(buf) > 2_000_000:
                        buf = buf[-2_000_000:]
                        break

                text = bytes(buf).decode("utf-8", errors="replace")
            else:
                # Linear fallback (bounded in practice by file size).
                text = f.read().decode("utf-8", errors="replace")

    except FileNotFoundError:
        return ""
    except Exception:
        return ""

    parts = text.splitlines()[-n:]
    return "\n".join(parts) + ("\n" if parts else "")


def mount_logs(app: FastAPI) -> None:
    # Tap LogBus once per process so the Logs UI can stream core log records
    # without tailing files.
    install_log_tap()

    @app.get("/api/logs/tail")
    def logs_tail(request: Request, lines: int = 200) -> dict[str, Any]:
        # Primary source: in-process EventBus tap (no tailing web logs).
        items = snapshot(since_id=0, limit=max(1, min(int(lines), 2000)))
        txt = "\n".join(payload for _eid, payload in items) + ("\n" if items else "")

        # Secondary (optional): core diagnostics JSONL sink file.
        resolver = _get_resolver(request)
        if is_diagnostics_enabled(resolver):
            fs = _get_file_service(resolver)
            if fs is not None:
                txt_file = _tail_jsonl(fs, max(1, min(int(lines), 2000)))
                if txt_file:
                    txt = txt + txt_file

        return {"path": "event_bus", "text": txt}

    @app.get("/api/logs/stream")
    def logs_stream(request: Request, since_id: int = 0) -> StreamingResponse:
        # SSE stream from the in-process EventBus tap.
        if since_id < 0:
            since_id = 0

        def gen() -> Iterator[bytes]:
            last = int(since_id)
            for eid, payload in stream(since_id=last):
                # Emit a JSON string as SSE data.
                data = payload.replace("\n", "\\n")
                if eid is None:
                    yield (f"event: heartbeat\ndata: {data}\n\n").encode()
                    continue
                last = int(eid)
                yield (f"id: {eid}\ndata: {data}\n\n").encode()

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.get("/api/logbus/tail")
    def logbus_tail(lines: int = 200) -> dict[str, Any]:
        # In-process LogBus tap (no tailing any files).
        n = max(1, min(int(lines), 2000))
        return {"path": "log_bus", "text": logbus_tail_text(lines=n)}

    @app.get("/api/logbus/stream")
    def logbus_stream(since_id: int = 0) -> StreamingResponse:
        if since_id < 0:
            since_id = 0

        def gen() -> Iterator[bytes]:
            last = int(since_id)
            for eid, line in logbus_iter(since_id=last):
                # Keep one record per SSE message. No embedded newlines.
                data = line.replace("\n", "\\n")
                if eid is None:
                    yield (f"event: heartbeat\ndata: {data}\n\n").encode()
                    continue
                last = int(eid)
                yield (f"id: {eid}\ndata: {data}\n\n").encode()

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.get("/api/logs/diagnostics_jsonl_tail")
    def logs_diagnostics_jsonl_tail(request: Request, lines: int = 200) -> dict[str, Any]:
        resolver = _get_resolver(request)
        if not is_diagnostics_enabled(resolver):
            raise HTTPException(status_code=404, detail="diagnostics not enabled")

        fs = _get_file_service(resolver)
        if fs is None:
            raise HTTPException(status_code=404, detail="stage_dir not configured")

        return {
            "path": f"{RootName.STAGE.value}:{DIAGNOSTICS_REL_PATH}",
            "text": _tail_jsonl(fs, max(1, min(int(lines), 5000))),
        }

    @app.get("/api/logs/diagnostics_jsonl_stream")
    def logs_diagnostics_jsonl_stream(request: Request) -> StreamingResponse:
        resolver = _get_resolver(request)
        if not is_diagnostics_enabled(resolver):
            raise HTTPException(status_code=404, detail="diagnostics not enabled")

        fs = _get_file_service(resolver)
        if fs is None:
            raise HTTPException(status_code=404, detail="stage_dir not configured")

        def gen() -> Iterator[bytes]:
            last = ""
            while True:
                txt = _tail_jsonl(fs, 200)
                if txt != last:
                    last = txt
                    payload = json.dumps(
                        {"text": txt}, ensure_ascii=True, separators=(",", ":"), sort_keys=True
                    )
                    yield ("data: " + payload + "\n\n").encode("utf-8")
                # Do not spin.
                __import__("time").sleep(1.0)

        return StreamingResponse(gen(), media_type="text/event-stream")
