from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path


def _import_ipc_controller():
    scripts_dir = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    from am_patch.ipc_socket import IpcController

    return IpcController


class _FakeLogger:
    def __init__(self) -> None:
        self.screen_level = "verbose"
        self.log_level = "verbose"
        self._stream = None

    def set_ipc_stream(self, cb):
        self._stream = cb

    def emit_control_event(self, payload):
        if self._stream is not None:
            self._stream({"seq": 1, **payload})


class _FakeStatus:
    def get_stage(self) -> str:
        return "PREFLIGHT"


def _open_client(socket_path: Path):
    deadline = time.monotonic() + 1.0
    while True:
        conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.settimeout(1.0)
        try:
            conn.connect(str(socket_path))
            fp = conn.makefile("rwb", buffering=0)
            first = json.loads(fp.readline().decode("utf-8"))
            assert first["type"] == "control"
            assert first["event"] == "connected"
            return conn, fp
        except (ConnectionRefusedError, FileNotFoundError, OSError):
            conn.close()
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.05)


def _read_control_event(fp, *, event: str) -> dict[str, object]:
    while True:
        msg = json.loads(fp.readline().decode("utf-8"))
        if msg.get("type") == "control" and msg.get("event") == event:
            return msg


def _send_cmd(
    fp,
    *,
    cmd: str,
    cmd_id: str,
    args: dict[str, object] | None = None,
) -> dict[str, object]:
    req = {
        "type": "cmd",
        "cmd": cmd,
        "cmd_id": cmd_id,
        "args": args or {},
    }
    fp.write((json.dumps(req, separators=(",", ":")) + "\n").encode("utf-8"))
    while True:
        msg = json.loads(fp.readline().decode("utf-8"))
        if msg.get("type") == "reply" and msg.get("cmd_id") == cmd_id:
            return msg


def test_ready_command_completes_startup_handshake(tmp_path: Path) -> None:
    ipc_controller_cls = _import_ipc_controller()
    socket_path = tmp_path / "am_patch_ready.sock"
    ipc = ipc_controller_cls(
        socket_path=socket_path,
        issue_id="1000",
        mode="workspace",
        status_provider=_FakeStatus(),
        logger=_FakeLogger(),
        handshake_enabled=True,
        handshake_wait_s=1,
    )
    ipc.start()
    try:
        conn, fp = _open_client(socket_path)
        try:
            reply = _send_cmd(fp, cmd="ready", cmd_id="c1")
            assert reply["ok"] is True
            assert ipc.wait_for_ready() is True
            assert ipc.startup_handshake_completed() is True
        finally:
            fp.close()
            conn.close()
    finally:
        ipc.stop()


def test_drain_ack_requires_matching_eos_seq(tmp_path: Path) -> None:
    ipc_controller_cls = _import_ipc_controller()
    socket_path = tmp_path / "am_patch_drain.sock"
    ipc = ipc_controller_cls(
        socket_path=socket_path,
        issue_id="1000",
        mode="workspace",
        status_provider=_FakeStatus(),
        logger=_FakeLogger(),
        handshake_enabled=True,
        handshake_wait_s=1,
    )
    ipc.start()
    try:
        conn, fp = _open_client(socket_path)
        try:
            ready_reply = _send_cmd(fp, cmd="ready", cmd_id="c1")
            assert ready_reply["ok"] is True
            assert ipc.begin_shutdown_handshake(eos_seq=7) is True

            bad_reply = _send_cmd(fp, cmd="drain_ack", cmd_id="c2", args={"seq": 6})
            assert bad_reply["ok"] is False
            assert bad_reply["error"]["code"] == "VALIDATION_ERROR"

            ok_reply = _send_cmd(fp, cmd="drain_ack", cmd_id="c3", args={"seq": 7})
            assert ok_reply["ok"] is True
            assert ipc.wait_for_drain_ack() is True
        finally:
            fp.close()
            conn.close()
    finally:
        ipc.stop()


def test_drain_ack_survives_idle_connection_on_same_socket(tmp_path: Path) -> None:
    ipc_controller_cls = _import_ipc_controller()
    socket_path = tmp_path / "am_patch_idle.sock"
    ipc = ipc_controller_cls(
        socket_path=socket_path,
        issue_id="1000",
        mode="workspace",
        status_provider=_FakeStatus(),
        logger=_FakeLogger(),
        handshake_enabled=True,
        handshake_wait_s=1,
    )
    ipc.start()
    try:
        conn, fp = _open_client(socket_path)
        try:
            ready_reply = _send_cmd(fp, cmd="ready", cmd_id="c1")
            assert ready_reply["ok"] is True
            assert ipc.wait_for_ready() is True

            time.sleep(1.2)
            assert ipc.begin_shutdown_handshake(eos_seq=7) is True
            ipc._on_log_event({"seq": 7, "type": "control", "event": "eos"})

            eos = _read_control_event(fp, event="eos")
            assert eos["seq"] == 7

            ok_reply = _send_cmd(fp, cmd="drain_ack", cmd_id="c2", args={"seq": 7})
            assert ok_reply["ok"] is True
            assert ipc.wait_for_drain_ack() is True
        finally:
            fp.close()
            conn.close()
    finally:
        ipc.stop()


def test_eof_removes_client_from_broadcast_list(tmp_path: Path) -> None:
    ipc_controller_cls = _import_ipc_controller()
    socket_path = tmp_path / "am_patch_cleanup.sock"
    ipc = ipc_controller_cls(
        socket_path=socket_path,
        issue_id="1000",
        mode="workspace",
        status_provider=_FakeStatus(),
        logger=_FakeLogger(),
        handshake_enabled=True,
        handshake_wait_s=1,
    )
    ipc.start()
    try:
        conn, fp = _open_client(socket_path)
        fp.close()
        conn.close()

        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            with ipc._clients_lock:
                if not ipc._clients:
                    break
            time.sleep(0.05)

        with ipc._clients_lock:
            assert ipc._clients == []
    finally:
        ipc.stop()
