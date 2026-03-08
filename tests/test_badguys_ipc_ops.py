from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path

from badguys.bdg_executor import execute_bdg_step
from badguys.bdg_loader import BdgStep
from badguys.bdg_materializer import MaterializedAssets
from badguys.bdg_ops_ipc import pop_ipc_plans, start_ipc_plan_threads, wait_for_ipc_plan_threads
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


def test_ipc_send_command_queue_writes_request_and_reply(tmp_path: Path) -> None:
    repo_root = tmp_path
    artifacts_dir = repo_root / "patches" / "badguys_logs" / "test_ipc"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    socket_path = repo_root / "patches" / "ipc.sock"
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    seen: list[dict[str, object]] = []
    server = _serve_once(socket_path, seen)

    step_runner_cfg = _step_runner_cfg(repo_root, artifacts_dir=artifacts_dir)
    result = execute_bdg_step(
        repo_root=repo_root,
        config_path=Path("badguys/config.toml"),
        cfg_runner_cmd=["python3", "scripts/am_patch.py"],
        subst=SubstCtx(issue_id="777", now_stamp="20260308_090000"),
        full_runner_tests=set(),
        step=BdgStep(op="IPC_SEND_COMMAND", params={"cmd": "ping"}),
        mats=MaterializedAssets(root=repo_root / "patches" / "mats", files={}),
        test_id="test_ipc",
        step_index=0,
        step_runner_cfg=step_runner_cfg,
    )
    handles = start_ipc_plan_threads(
        plans=pop_ipc_plans(step_runner_cfg),
        socket_path=socket_path,
        ipc_stream_path=artifacts_dir / "runner.ipc.step1.jsonl",
        artifacts_dir=artifacts_dir,
    )
    wait_for_ipc_plan_threads(handles=handles, timeout_s=3.0)
    server.join(timeout=3.0)

    request_path = artifacts_dir / "ipc_request.step0.json"
    reply_path = artifacts_dir / "ipc_reply.step0.json"
    assert result.rc == 0
    assert request_path.exists()
    assert reply_path.exists()
    assert seen[0]["cmd"] == "ping"
    assert json.loads(reply_path.read_text(encoding="utf-8"))["ok"] is True


def test_ipc_send_command_can_wait_for_event_and_map_args(tmp_path: Path) -> None:
    repo_root = tmp_path
    artifacts_dir = repo_root / "patches" / "badguys_logs" / "test_ipc"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    ipc_stream_path = artifacts_dir / "runner.ipc.step1.jsonl"
    socket_path = repo_root / "patches" / "ipc.sock"
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    seen: list[dict[str, object]] = []
    server = _serve_once(socket_path, seen)

    step_runner_cfg = _step_runner_cfg(repo_root, artifacts_dir=artifacts_dir)
    execute_bdg_step(
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
    handles = start_ipc_plan_threads(
        plans=pop_ipc_plans(step_runner_cfg),
        socket_path=socket_path,
        ipc_stream_path=ipc_stream_path,
        artifacts_dir=artifacts_dir,
    )
    time.sleep(0.1)
    ipc_stream_path.write_text(
        '{"type":"control","event":"eos","seq":5}\n',
        encoding="utf-8",
    )
    wait_for_ipc_plan_threads(handles=handles, timeout_s=3.0)
    server.join(timeout=3.0)

    assert seen[0]["cmd"] == "drain_ack"
    assert seen[0]["args"] == {"seq": 5}
    reply_obj = json.loads((artifacts_dir / "ipc_reply.step2.json").read_text(encoding="utf-8"))
    assert reply_obj["ok"] is True
