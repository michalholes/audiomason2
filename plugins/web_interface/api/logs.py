from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Iterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from ..util.paths import log_path_default


def _tail(path: Path, lines: int) -> str:
    if not path.exists():
        return ""
    data = path.read_text(encoding="utf-8", errors="replace")
    parts = data.splitlines()[-lines:]
    return "\n".join(parts) + ("\n" if parts else "")


def mount_logs(app: FastAPI) -> None:
    @app.get("/api/logs/tail")
    def logs_tail(lines: int = 200) -> dict[str, Any]:
        p = log_path_default()
        if not p:
            return {"path": None, "text": ""}
        return {"path": str(p), "text": _tail(p, max(1, min(lines, 5000)))}

    @app.get("/api/logs/stream")
    def logs_stream() -> StreamingResponse:
        p = log_path_default()
        if not p:
            raise HTTPException(status_code=404, detail="WEB_INTERFACE_LOG_PATH not set")

        def gen() -> Iterator[bytes]:
            last = ""
            while True:
                txt = _tail(p, 200)
                if txt != last:
                    last = txt
                    payload = txt.replace("\n", "\\n")
                    yield ("data: " + payload + "\n\n").encode("utf-8")
                time.sleep(1.0)

        return StreamingResponse(gen(), media_type="text/event-stream")
