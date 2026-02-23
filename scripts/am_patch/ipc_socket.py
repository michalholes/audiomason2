from __future__ import annotations

import contextlib
import json
import os
import socket
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROTOCOL = "am_patch_ipc/1"
DEFAULT_SOCKET_NAME = "am_patch.sock"


_LEVELS = ("quiet", "normal", "warning", "verbose", "debug")


def _normalize_level(v: str) -> str:
    lvl = str(v or "").strip().lower()
    return lvl if lvl in _LEVELS else "verbose"


def _safe_unlink(path: Path) -> None:
    try:
        if path.exists() or path.is_symlink():
            path.unlink()
    except Exception:
        pass


def _json_line(obj: dict[str, Any]) -> bytes:
    return (json.dumps(obj, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")


def _system_runtime_dir() -> Path:
    uid = os.getuid()
    candidates = [
        Path("/run/user") / str(uid),
        Path("/run"),
        Path("/tmp"),
    ]
    for c in candidates:
        try:
            c.mkdir(parents=True, exist_ok=True)
            test = c / ".am_patch_ipc_probe"
            test.write_text("x", encoding="utf-8")
            test.unlink()
            return c
        except Exception:
            continue
    return Path(".")


@dataclass
class IpcState:
    paused: bool = False
    cancel: bool = False
    stop_after_step: str | None = None
    pause_after_step: str | None = None


class IpcController:
    def __init__(
        self,
        *,
        socket_path: Path,
        issue_id: str | None,
        mode: str,
        status_provider: Any,
        logger: Any,
    ) -> None:
        self.socket_path = socket_path
        self.issue_id = issue_id
        self.mode = mode
        self._status_provider = status_provider
        self._logger = logger

        self._state = IpcState()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._resume = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._serve, name="am_patch_ipc", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._resume.set()
        t = self._thread
        if t is not None:
            t.join(timeout=2.0)
        self._thread = None
        _safe_unlink(self.socket_path)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            st = IpcState(
                paused=self._state.paused,
                cancel=self._state.cancel,
                stop_after_step=self._state.stop_after_step,
                pause_after_step=self._state.pause_after_step,
            )
        stage = "PREFLIGHT"
        try:
            stage = str(self._status_provider.get_stage() or "PREFLIGHT")
        except Exception:
            stage = "PREFLIGHT"
        return {
            "protocol": PROTOCOL,
            "issue_id": self.issue_id,
            "mode": self.mode,
            "stage": stage,
            "paused": st.paused,
            "cancel": st.cancel,
            "stop_after_step": st.stop_after_step,
            "pause_after_step": st.pause_after_step,
            "verbosity": getattr(self._logger, "screen_level", "verbose"),
            "log_level": getattr(self._logger, "log_level", "verbose"),
        }

    def request_cancel(self) -> None:
        with self._lock:
            self._state.cancel = True
        self._resume.set()

    def request_resume(self) -> None:
        with self._lock:
            self._state.paused = False
        self._resume.set()

    def request_pause_now(self) -> None:
        with self._lock:
            self._state.paused = True
        self._resume.clear()

    def set_stop_after_step(self, step: str | None) -> None:
        with self._lock:
            self._state.stop_after_step = str(step).strip() if step else None

    def set_pause_after_step(self, step: str | None) -> None:
        with self._lock:
            self._state.pause_after_step = str(step).strip() if step else None

    def set_verbosity(self, *, verbosity: str | None = None, log_level: str | None = None) -> None:
        if verbosity is not None:
            self._logger.screen_level = _normalize_level(verbosity)
        if log_level is not None:
            self._logger.log_level = _normalize_level(log_level)

    def check_boundary(self, *, completed_step: str) -> str | None:
        step = str(completed_step or "").strip()
        if not step:
            return None
        with self._lock:
            if self._state.cancel:
                return "cancel"
            if self._state.stop_after_step and self._state.stop_after_step == step:
                self._state.cancel = True
                return "stop_after_step"
            if self._state.pause_after_step and self._state.pause_after_step == step:
                self._state.paused = True
                self._resume.clear()
                return "pause_after_step"
        return None

    def wait_if_paused(self) -> None:
        while True:
            with self._lock:
                paused = self._state.paused
                cancelled = self._state.cancel
            if cancelled or not paused:
                return
            # main thread waits; IPC thread remains active
            self._resume.wait(0.25)

    def _serve(self) -> None:
        sock_path = self.socket_path
        sock_path.parent.mkdir(parents=True, exist_ok=True)
        _safe_unlink(sock_path)

        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            srv.bind(str(sock_path))
            srv.listen(1)
            srv.settimeout(0.25)
        except Exception:
            with contextlib.suppress(Exception):
                srv.close()
            return

        while not self._stop.is_set():
            try:
                conn, _addr = srv.accept()
            except TimeoutError:
                continue
            except Exception:
                break
            try:
                conn.settimeout(1.0)
                fp = conn.makefile("rwb", buffering=0)
                buf = b""
                while not self._stop.is_set():
                    try:
                        chunk = fp.readline()
                    except TimeoutError:
                        continue
                    except Exception:
                        break
                    if not chunk:
                        break
                    buf = chunk.strip()
                    if not buf:
                        continue
                    try:
                        req = json.loads(buf.decode("utf-8", errors="strict"))
                    except Exception:
                        fp.write(
                            _json_line({"protocol": PROTOCOL, "ok": False, "error": "bad_json"})
                        )
                        continue

                    if str(req.get("protocol", "")) != PROTOCOL:
                        fp.write(
                            _json_line(
                                {
                                    "protocol": PROTOCOL,
                                    "ok": False,
                                    "error": "bad_protocol",
                                }
                            )
                        )
                        continue

                    cmd = str(req.get("cmd", "")).strip()
                    if cmd == "ping":
                        fp.write(_json_line({"protocol": PROTOCOL, "ok": True, "reply": "pong"}))
                        continue
                    if cmd == "get_state":
                        fp.write(_json_line({"ok": True, **self.snapshot()}))
                        continue
                    if cmd == "cancel":
                        self.request_cancel()
                        fp.write(_json_line({"protocol": PROTOCOL, "ok": True}))
                        continue
                    if cmd == "resume":
                        self.request_resume()
                        fp.write(_json_line({"protocol": PROTOCOL, "ok": True}))
                        continue
                    if cmd == "pause_after_step":
                        step = req.get("step")
                        self.set_pause_after_step(str(step) if step is not None else None)
                        fp.write(_json_line({"protocol": PROTOCOL, "ok": True}))
                        continue
                    if cmd == "stop_after_step":
                        step = req.get("step")
                        self.set_stop_after_step(str(step) if step is not None else None)
                        fp.write(_json_line({"protocol": PROTOCOL, "ok": True}))
                        continue
                    if cmd == "pause":
                        self.request_pause_now()
                        fp.write(_json_line({"protocol": PROTOCOL, "ok": True}))
                        continue
                    if cmd == "set_verbosity":
                        v = req.get("verbosity")
                        log_level_value = req.get("log_level")
                        self.set_verbosity(
                            verbosity=(str(v) if v is not None else None),
                            log_level=(
                                str(log_level_value) if log_level_value is not None else None
                            ),
                        )
                        fp.write(_json_line({"protocol": PROTOCOL, "ok": True}))
                        continue

                    fp.write(
                        _json_line({"protocol": PROTOCOL, "ok": False, "error": "unknown_cmd"})
                    )
            finally:
                with contextlib.suppress(Exception):
                    conn.close()

        try:
            srv.close()
        finally:
            _safe_unlink(sock_path)


def resolve_socket_path(
    *,
    policy: Any,
    patch_dir: Path,
) -> Path | None:
    enabled = bool(getattr(policy, "ipc_socket_enabled", True))
    if not enabled:
        return None

    mode = str(getattr(policy, "ipc_socket_mode", "patch_dir") or "patch_dir").strip().lower()
    name = str(getattr(policy, "ipc_socket_name", DEFAULT_SOCKET_NAME) or DEFAULT_SOCKET_NAME)

    if "/" in name or "\\" in name or name.strip() != name:
        name = DEFAULT_SOCKET_NAME

    if mode == "patch_dir":
        return patch_dir / name

    if mode == "base_dir":
        base = getattr(policy, "ipc_socket_base_dir", None)
        if not base:
            return None
        return Path(str(base)) / name

    if mode == "system_runtime":
        base = getattr(policy, "ipc_socket_system_runtime_dir", None)
        if base:
            return Path(str(base)) / name
        return _system_runtime_dir() / name

    # Unknown mode -> disabled to avoid surprises.
    return None
