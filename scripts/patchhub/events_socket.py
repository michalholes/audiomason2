from __future__ import annotations

import contextlib
import json
import socket
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

_PROTOCOL = "am_patch_ipc/1"


def job_socket_path(job_id: str) -> str:
    return str(Path("/tmp/audiomason") / f"patchhub_{job_id}.sock")


def iter_socket_lines(
    socket_path: str,
    *,
    connect_timeout_s: float,
    retry_sleep_s: float,
) -> Iterator[str]:
    """Yield NDJSON lines from the runner IPC socket.

    connect_timeout_s: max total time spent retrying connect.
    retry_sleep_s: sleep interval between retries.

    The iterator yields raw text lines without the trailing newline.
    """

    deadline = None
    if connect_timeout_s is not None and connect_timeout_s > 0:
        deadline = connect_timeout_s

    remaining = deadline
    while True:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(1.0)
            s.connect(socket_path)
            fp = s.makefile("rb", buffering=0)
            try:
                while True:
                    raw = fp.readline()
                    if not raw:
                        return
                    try:
                        line = raw.decode("utf-8")
                    except Exception:
                        line = raw.decode("utf-8", errors="replace")
                    line = line.rstrip("\n")
                    if not line.strip():
                        continue
                    yield line
            finally:
                with contextlib.suppress(Exception):
                    fp.close()
                with contextlib.suppress(Exception):
                    s.close()
        except FileNotFoundError:
            pass
        except ConnectionRefusedError:
            pass
        except OSError:
            pass

        if remaining is not None:
            remaining -= retry_sleep_s
            if remaining <= 0:
                return

        time.sleep(retry_sleep_s)


def send_cancel(socket_path: str) -> bool:
    """Send cancel to the runner IPC socket.

    Returns True if the request was written and an ok reply was observed.
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
            # Read replies until we see ours or connection closes.
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
