from __future__ import annotations

import json
import socket
import time
from pathlib import Path
from typing import Any


def _validate_result(obj: Any) -> dict[str, Any] | None:
    if not isinstance(obj, dict):
        return None
    if "ok" not in obj or "return_code" not in obj:
        return None
    ok = obj.get("ok")
    rc = obj.get("return_code")
    if not isinstance(ok, bool):
        return None
    if not isinstance(rc, int):
        return None

    out: dict[str, Any] = {"ok": ok, "return_code": rc}
    lp = obj.get("log_path")
    jp = obj.get("json_path")
    if isinstance(lp, str) and lp:
        out["log_path"] = lp
    if isinstance(jp, str) and jp:
        out["json_path"] = jp
    return out


def record_ipc_stream(
    socket_path: Path,
    *,
    out_path: Path,
    connect_timeout_s: float,
    total_timeout_s: float,
) -> tuple[dict[str, Any] | None, str]:
    """Record the full runner IPC NDJSON stream and compute runner value_text.

    Returns: (validated_result_or_none, value_text)

    - out_path receives the exact NDJSON lines read from the socket (no filtering).
    - value_text is concatenation of obj['msg'] for all type='log' events, joined by '\n'.
    """

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Ensure the file exists even if connection fails.
    out_path.open("w", encoding="utf-8", newline="\n").close()

    connect_deadline = time.monotonic() + max(0.0, float(connect_timeout_s))
    total_deadline: float | None
    if float(total_timeout_s) > 0:
        total_deadline = time.monotonic() + float(total_timeout_s)
    else:
        total_deadline = None

    s: socket.socket | None = None
    while True:
        if time.monotonic() >= connect_deadline:
            return None, ""
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.2)
            s.connect(str(socket_path))
            break
        except (FileNotFoundError, ConnectionRefusedError, OSError):
            try:
                if s is not None:
                    s.close()
            except Exception:
                pass
            time.sleep(0.05)
            continue

    value_msgs: list[str] = []
    result: dict[str, Any] | None = None

    try:
        s.settimeout(0.2)
        fp = s.makefile("r", encoding="utf-8", newline="\n")
        with out_path.open("a", encoding="utf-8", newline="\n") as out_fp:
            while True:
                if total_deadline is not None and time.monotonic() >= total_deadline:
                    break
                try:
                    line = fp.readline()
                except (OSError, ValueError):
                    break
                if not line:
                    break

                # Stream persistence rule: write exact lines.
                out_fp.write(line)

                try:
                    obj = json.loads(line)
                except Exception:
                    continue

                if isinstance(obj, dict) and obj.get("type") == "log":
                    msg = obj.get("msg")
                    if isinstance(msg, str):
                        value_msgs.append(msg)

                if isinstance(obj, dict) and obj.get("type") == "result":
                    valid = _validate_result(obj)
                    if valid is not None:
                        result = valid

    finally:
        try:
            if s is not None:
                s.close()
        except Exception:
            pass

    value_text = "\n".join(value_msgs)
    return result, value_text
