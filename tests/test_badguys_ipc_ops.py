from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path

from badguys.bdg_executor import execute_bdg_step
from badguys.bdg_loader import BdgStep
from badguys.bdg_materializer import MaterializedAssets
from badguys.bdg_ops_ipc import pop_ipc_plans, send_ipc_command
from badguys.bdg_subst import SubstCtx


def _serve_once(socket_path: Path, seen: list[dict[str, object]]) -> threading.Thread:
    def _target() -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as srv:
            srv.bind(str(socket_path))
            srv.listen(1)
            conn, _ = srv.accept()
            with conn:
                fp = conn.makefile("rwb", buffering=0)
                fp.write(b'{"type":"control","event":"connected"}\n')
                line = fp.readline()
                req = json.loads(line.decode("utf-8"))
                seen.append(req)
                reply = {
                    "type": "reply",
                    "cmd_id": req["cmd_id"],
                    "ok": True,
                    "data": {"seen_cmd": req["cmd"]},
                }
                fp.write((json.dumps(reply, ensure_ascii=True) + "\n").encode("utf-8"))

    thread = threading.Thread(target=_target, name="ipc_test_server", daemon=True)
    thread.start()
    return thread


def _step_runner_cfg(repo_root: Path, *, artifacts_dir: Path) -> dict[str, object]:
    return {
        "artifacts_dir": artifacts_dir,
        "console_verbosity": "quiet",
        "copy_runner_log": False,
        "patches_dir": repo_root / "patches",
        "write_subprocess_stdio": False,
    }


def test_ipc_send_command_queues_plan_with_event_mapping(tmp_path: Path) -> None:
    repo_root = tmp_path
    artifacts_dir = repo_root / "patches" / "badguys_logs" / "test_ipc"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    step_runner_cfg = _step_runner_cfg(repo_root, artifacts_dir=artifacts_dir)
    result = execute_bdg_step(
        repo_root=repo_root,
        config_path=Path("badguys/config.toml"),
        cfg_runner_cmd=["python3", "scripts/am_patch.py"],
        subst=SubstCtx(issue_id="777", now_stamp="20260308_090000"),
        full_runner_tests=set(),
        step=BdgStep(
            op="IPC_SEND_COMMAND",
            params={
                "cmd": "drain_ack",
                "wait_event_type": "control",
                "wait_event_name": "eos",
                "event_arg_map": {"seq": "seq"},
            },
        ),
        mats=MaterializedAssets(root=repo_root / "patches" / "mats", files={}),
        test_id="test_ipc",
        step_index=2,
        step_runner_cfg=step_runner_cfg,
    )

    plans = pop_ipc_plans(step_runner_cfg)

    assert result.rc == 0
    assert result.value == "queued:ipc_reply.step2.json"
    assert len(plans) == 1
    assert plans[0].cmd == "drain_ack"
    assert plans[0].wait_event_type == "control"
    assert plans[0].wait_event_name == "eos"
    assert plans[0].event_arg_map == {"seq": "seq"}


def test_send_ipc_command_returns_reply(tmp_path: Path) -> None:
    repo_root = tmp_path
    socket_path = repo_root / "patches" / "ipc.sock"
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    seen: list[dict[str, object]] = []
    server = _serve_once(socket_path, seen)

    reply = send_ipc_command(
        socket_path=socket_path,
        cmd="ping",
        args={},
        cmd_id="test_ping_1",
        connect_timeout_s=3.0,
        reply_timeout_s=3.0,
    )
    server.join(timeout=3.0)

    assert seen[0]["cmd"] == "ping"
    assert reply["ok"] is True
    assert reply["data"] == {"seen_cmd": "ping"}


def test_record_ipc_stream_copies_result_artifact_before_source_disappears(
    tmp_path: Path,
) -> None:
    from badguys.ipc_stream_recorder import record_ipc_stream

    socket_path = tmp_path / "ipc.sock"
    result_src = tmp_path / "result.jsonl"
    result_src.write_text('{"ok":true}\n', encoding="utf-8")
    copied_path = tmp_path / "artifacts" / "runner.result.json"

    def _target() -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as srv:
            srv.bind(str(socket_path))
            srv.listen(1)
            conn, _ = srv.accept()
            with conn:
                fp = conn.makefile("rwb", buffering=0)
                result = {
                    "type": "result",
                    "ok": True,
                    "return_code": 0,
                    "json_path": str(result_src),
                }
                fp.write((json.dumps(result) + "\n").encode("utf-8"))
                time.sleep(0.05)
                result_src.unlink()

    server = threading.Thread(target=_target, name="ipc_result_copy_server", daemon=True)
    server.start()

    result, value_text, artifact_copy = record_ipc_stream(
        socket_path,
        out_path=tmp_path / "runner.ipc.jsonl",
        connect_timeout_s=3.0,
        total_timeout_s=3.0,
        result_json_copy_path=copied_path,
    )
    server.join(timeout=3.0)

    assert result == {"ok": True, "return_code": 0, "json_path": str(result_src)}
    assert value_text == ""
    assert artifact_copy == {"ok": True, "error": None}
    assert copied_path.read_text(encoding="utf-8") == '{"ok":true}\n'
    assert not result_src.exists()


def test_record_ipc_stream_falls_back_to_ipc_stream_when_result_artifact_is_missing(
    tmp_path: Path,
) -> None:
    from badguys.ipc_stream_recorder import record_ipc_stream

    socket_path = tmp_path / "ipc.sock"
    missing_src = tmp_path / "missing.jsonl"

    def _target() -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as srv:
            srv.bind(str(socket_path))
            srv.listen(1)
            conn, _ = srv.accept()
            with conn:
                fp = conn.makefile("rwb", buffering=0)
                result = {
                    "type": "result",
                    "ok": True,
                    "return_code": 0,
                    "json_path": str(missing_src),
                }
                fp.write((json.dumps(result) + "\n").encode("utf-8"))

    server = threading.Thread(target=_target, name="ipc_missing_result_server", daemon=True)
    server.start()

    out_path = tmp_path / "runner.ipc.jsonl"
    copied_path = tmp_path / "artifacts" / "runner.result.json"

    _, _, artifact_copy = record_ipc_stream(
        socket_path,
        out_path=out_path,
        connect_timeout_s=3.0,
        total_timeout_s=3.0,
        result_json_copy_path=copied_path,
    )
    server.join(timeout=3.0)

    assert artifact_copy == {"ok": True, "error": None}
    copied_text = copied_path.read_text(encoding="utf-8")
    assert copied_text == out_path.read_text(encoding="utf-8")
    copied_obj = json.loads(copied_text)
    assert copied_obj["json_path"] == str(missing_src)
