from __future__ import annotations

import json
import select
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


def _iter_socket_candidates(socket_path: Path) -> list[Path]:
    root_candidate = socket_path
    root_dir = socket_path.parent
    socket_name = socket_path.name

    candidates: list[Path] = [root_candidate]
    seen = {root_candidate}

    try:
        for path in sorted(root_dir.rglob(socket_name)):
            if path in seen:
                continue
            seen.add(path)
            candidates.append(path)
    except FileNotFoundError:
        return candidates

    return candidates


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
        connected = False
        for candidate in _iter_socket_candidates(socket_path):
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(0.2)
                s.connect(str(candidate))
                connected = True
                break
            except (FileNotFoundError, ConnectionRefusedError, OSError):
                try:
                    if s is not None:
                        s.close()
                except Exception:
                    pass
                s = None
                continue
        if connected:
            break
        time.sleep(0.005)

    value_msgs: list[str] = []
    result: dict[str, Any] | None = None

    def _handle_line(line: str, *, out_fp: Any) -> None:
        nonlocal result

        # Stream persistence rule: write exact lines.
        out_fp.write(line)

        try:
            obj = json.loads(line)
        except Exception:
            return

        if isinstance(obj, dict) and obj.get("type") == "log":
            msg = obj.get("msg")
            if isinstance(msg, str):
                value_msgs.append(msg)

        if isinstance(obj, dict) and obj.get("type") == "result":
            valid = _validate_result(obj)
            if valid is not None:
                result = valid

    if s is None:
        return None, ""

    try:
        s.setblocking(False)
        pending = ""
        with out_path.open("a", encoding="utf-8", newline="\n") as out_fp:
            while True:
                wait_s: float | None
                if total_deadline is None:
                    wait_s = None
                else:
                    wait_s = max(0.0, total_deadline - time.monotonic())
                    if wait_s == 0.0:
                        break

                try:
                    readable, _, _ = select.select([s], [], [], wait_s)
                except (OSError, ValueError):
                    break
                if not readable:
                    break

                try:
                    chunk = s.recv(65536)
                except BlockingIOError:
                    continue
                except OSError:
                    break
                if not chunk:
                    break

                pending += chunk.decode("utf-8", errors="replace")
                while True:
                    newline_at = pending.find("\n")
                    if newline_at < 0:
                        break
                    line = pending[: newline_at + 1]
                    pending = pending[newline_at + 1 :]
                    _handle_line(line, out_fp=out_fp)

            if pending:
                _handle_line(pending, out_fp=out_fp)

    finally:
        try:
            if s is not None:
                s.close()
        except Exception:
            pass

    value_text = "\n".join(value_msgs)
    return result, value_text
