from __future__ import annotations

import json
import socket
import sys
import threading
import time
from pathlib import Path

from badguys.ipc_stream_recorder import record_ipc_stream


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


def test_record_ipc_stream_handles_shutdown_drain_ack(tmp_path: Path) -> None:
    ipc_controller_cls = _import_ipc_controller()
    socket_path = tmp_path / "am_patch_drain_stream.sock"
    out_path = tmp_path / "stream.jsonl"
    logger = _FakeLogger()
    ipc = ipc_controller_cls(
        socket_path=socket_path,
        issue_id="1000",
        mode="workspace",
        status_provider=_FakeStatus(),
        logger=logger,
        handshake_enabled=True,
        handshake_wait_s=1,
    )
    ipc.start()
    try:
        result_holder: dict[str, tuple[dict[str, object] | None, str]] = {}
        command_plans = [
            {
                "protocol": "am_patch_ipc/1",
                "step_index": 0,
                "cmd": "ready",
                "cmd_id": "ready_1",
                "args": {},
                "delay_s": 0.0,
                "wait_event_type": None,
                "wait_event_name": None,
                "event_arg_map": {},
                "request_path": tmp_path / "req_ready.json",
                "reply_path": tmp_path / "reply_ready.json",
            },
            {
                "protocol": "am_patch_ipc/1",
                "step_index": 1,
                "cmd": "drain_ack",
                "cmd_id": "drain_1",
                "args": {},
                "delay_s": 0.0,
                "wait_event_type": "control",
                "wait_event_name": "eos",
                "event_arg_map": {"seq": "seq"},
                "request_path": tmp_path / "req_drain.json",
                "reply_path": tmp_path / "reply_drain.json",
            },
        ]

        def _run_recorder() -> None:
            result_holder["value"] = record_ipc_stream(
                socket_path,
                out_path=out_path,
                connect_timeout_s=1.0,
                total_timeout_s=0.0,
                command_plans=command_plans,
            )

        recorder = threading.Thread(target=_run_recorder, daemon=True)
        recorder.start()

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if ipc.startup_handshake_completed():
                break
            time.sleep(0.01)
        assert ipc.startup_handshake_completed() is True

        assert ipc.begin_shutdown_handshake(eos_seq=1) is True
        logger.emit_control_event({"type": "control", "event": "eos"})
        assert ipc.wait_for_drain_ack() is True
        ipc.stop()

        recorder.join(timeout=1.0)
        reply = json.loads((tmp_path / "reply_drain.json").read_text(encoding="utf-8"))

        assert recorder.is_alive() is False
        assert reply["ok"] is True
        assert reply["data"] == {"seq": 1}
    finally:
        ipc.stop()
