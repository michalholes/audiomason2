from __future__ import annotations

import contextlib
import json
import socket
import uuid
from pathlib import Path
from typing import Any

_PROTOCOL = "am_patch_ipc/1"


def job_socket_path(job_id: str) -> str:
    return str(Path("/tmp/audiomason") / f"patchhub_{job_id}.sock")


def send_cancel_sync(socket_path: str) -> bool:
    """Send cancel to runner IPC socket (synchronous).

    The async backend uses an async event pump, but cancellation needs an
    immediate boolean result to preserve the existing API contract.
    """

    cmd_id = "patchhub_" + uuid.uuid4().hex
    req: dict[str, Any] = {
        "protocol": _PROTOCOL,
        "type": "cmd",
        "cmd_id": cmd_id,
        "cmd": "cancel",
        "args": {},
    }
    payload = (json.dumps(req, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")

    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect(socket_path)
        fp = s.makefile("rwb", buffering=0)
        try:
            fp.write(payload)
            while True:
                raw = fp.readline()
                if not raw:
                    return False
                try:
                    line = raw.decode("utf-8")
                except Exception:
                    line = raw.decode("utf-8", errors="replace")
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                if str(obj.get("type", "")) != "reply":
                    continue
                if str(obj.get("cmd_id", "")) != cmd_id:
                    continue
                return bool(obj.get("ok") is True)
        finally:
            with contextlib.suppress(Exception):
                fp.close()
            with contextlib.suppress(Exception):
                s.close()
    except Exception:
        return False
