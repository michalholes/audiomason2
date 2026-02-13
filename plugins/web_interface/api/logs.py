from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from audiomason.core.config import ConfigError, ConfigResolver
from audiomason.core.diagnostics import is_diagnostics_enabled

from ..util.diag_stream import snapshot, stream


def _get_resolver(request: Request) -> ConfigResolver:
    resolver = getattr(request.app.state, "config_resolver", None)
    if isinstance(resolver, ConfigResolver):
        return resolver
    return ConfigResolver()


def _diagnostics_jsonl_path(resolver: ConfigResolver) -> Path | None:
    try:
        stage_dir, _src = resolver.resolve("stage_dir")
    except ConfigError:
        return None
    return Path(str(stage_dir)) / "diagnostics" / "diagnostics.jsonl"


def _tail_jsonl(path: Path, lines: int) -> str:
    if not path.exists():
        return ""
    data = path.read_text(encoding="utf-8", errors="replace")
    parts = data.splitlines()[-lines:]
    return "\n".join(parts) + ("\n" if parts else "")


def mount_logs(app: FastAPI) -> None:
    @app.get("/api/logs/tail")
    def logs_tail(request: Request, lines: int = 200) -> dict[str, Any]:
        # Primary source: in-process EventBus tap (no tailing web logs).
        items = snapshot(since_id=0, limit=max(1, min(int(lines), 2000)))
        txt = "\n".join(payload for _eid, payload in items) + ("\n" if items else "")

        # Secondary (optional): core diagnostics JSONL sink file.
        resolver = _get_resolver(request)
        if is_diagnostics_enabled(resolver):
            p = _diagnostics_jsonl_path(resolver)
            if p is not None:
                txt_file = _tail_jsonl(p, max(1, min(int(lines), 2000)))
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
                last = eid
                # Emit a JSON string as SSE data.
                data = payload.replace("\n", "\\n")
                yield (f"id: {eid}\ndata: {data}\n\n").encode()

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.get("/api/logs/diagnostics_jsonl_tail")
    def logs_diagnostics_jsonl_tail(request: Request, lines: int = 200) -> dict[str, Any]:
        resolver = _get_resolver(request)
        if not is_diagnostics_enabled(resolver):
            raise HTTPException(status_code=404, detail="diagnostics not enabled")

        p = _diagnostics_jsonl_path(resolver)
        if p is None:
            raise HTTPException(status_code=404, detail="stage_dir not configured")

        return {"path": str(p), "text": _tail_jsonl(p, max(1, min(int(lines), 5000)))}

    @app.get("/api/logs/diagnostics_jsonl_stream")
    def logs_diagnostics_jsonl_stream(request: Request) -> StreamingResponse:
        resolver = _get_resolver(request)
        if not is_diagnostics_enabled(resolver):
            raise HTTPException(status_code=404, detail="diagnostics not enabled")
        p = _diagnostics_jsonl_path(resolver)
        if p is None:
            raise HTTPException(status_code=404, detail="stage_dir not configured")

        def gen() -> Iterator[bytes]:
            last = ""
            while True:
                txt = _tail_jsonl(p, 200)
                if txt != last:
                    last = txt
                    payload = json.dumps(
                        {"text": txt}, ensure_ascii=True, separators=(",", ":"), sort_keys=True
                    )
                    yield ("data: " + payload + "\n\n").encode("utf-8")
                # Do not spin.
                __import__("time").sleep(1.0)

        return StreamingResponse(gen(), media_type="text/event-stream")
