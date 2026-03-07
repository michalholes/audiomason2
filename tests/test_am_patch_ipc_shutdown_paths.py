from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_runner_script_module():
    scripts_dir = Path(__file__).parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    os.environ["AM_PATCH_VENV_BOOTSTRAPPED"] = "1"
    script_path = scripts_dir / "am_patch.py"
    module_name = "am_patch_runner_test_module"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeLogger:
    def __init__(self) -> None:
        self.debug_messages: list[str] = []
        self.control_events: list[dict[str, object]] = []
        self._last_seq = 0

    def emit(self, **kwargs) -> None:
        self.debug_messages.append(str(kwargs.get("message", "")))

    def emit_control_event(self, payload: dict[str, object]) -> None:
        self._last_seq += 1
        self.control_events.append(dict(payload))

    def get_last_json_seq(self) -> int:
        return self._last_seq


class _FakeIpc:
    def __init__(self, *, startup_done: bool) -> None:
        self.startup_done = startup_done
        self.begin_calls: list[int] = []
        self.wait_calls = 0
        self.stop_calls = 0

    def startup_handshake_completed(self) -> bool:
        return self.startup_done

    def begin_shutdown_handshake(self, *, eos_seq: int) -> bool:
        self.begin_calls.append(eos_seq)
        return self.startup_done

    def wait_for_drain_ack(self) -> bool:
        self.wait_calls += 1
        return True

    def stop(self) -> None:
        self.stop_calls += 1


@pytest.mark.parametrize(
    ("mode", "test_mode"),
    [
        ("workspace", False),
        ("workspace", True),
        ("finalize", False),
        ("finalize_workspace", False),
    ],
)
def test_main_shutdown_handshake_runs_from_all_supported_modes(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    test_mode: bool,
) -> None:
    mod = _load_runner_script_module()
    logger = _FakeLogger()
    ipc = _FakeIpc(startup_done=True)
    cli = SimpleNamespace(mode=mode)
    policy = SimpleNamespace(
        ipc_socket_cleanup_delay_success_s=3,
        ipc_socket_cleanup_delay_failure_s=7,
        test_mode=test_mode,
    )
    ctx = SimpleNamespace(cli=cli, policy=policy, logger=logger, ipc=ipc)

    monkeypatch.setattr(
        mod, "build_effective_policy", lambda argv: (cli, policy, Path("cfg"), "cfg")
    )
    monkeypatch.setattr(mod, "build_paths_and_logger", lambda *args: ctx)
    monkeypatch.setattr(mod, "run_mode", lambda run_ctx: {"ok": True, "mode": run_ctx.cli.mode})
    monkeypatch.setattr(mod, "finalize_and_report", lambda run_ctx, result: 0)

    rc = mod.main([])

    assert rc == 0
    assert logger.control_events == [{"type": "control", "event": "eos"}]
    assert ipc.begin_calls == [1]
    assert ipc.wait_calls == 1
    assert ipc.stop_calls == 1
    assert any("drain_ack" in msg for msg in logger.debug_messages)


@pytest.mark.parametrize(("exit_code", "expected_delay"), [(0, 3.0), (2, 7.0)])
def test_main_falls_back_to_legacy_cleanup_delay_without_startup_ready(
    monkeypatch: pytest.MonkeyPatch,
    exit_code: int,
    expected_delay: float,
) -> None:
    mod = _load_runner_script_module()
    logger = _FakeLogger()
    ipc = _FakeIpc(startup_done=False)
    cli = SimpleNamespace(mode="workspace")
    policy = SimpleNamespace(
        ipc_socket_cleanup_delay_success_s=3,
        ipc_socket_cleanup_delay_failure_s=7,
        test_mode=False,
    )
    ctx = SimpleNamespace(cli=cli, policy=policy, logger=logger, ipc=ipc)
    waits: list[float] = []

    class _FakeEvent:
        def wait(self, seconds: float) -> bool:
            waits.append(float(seconds))
            return True

    monkeypatch.setattr(
        mod, "build_effective_policy", lambda argv: (cli, policy, Path("cfg"), "cfg")
    )
    monkeypatch.setattr(mod, "build_paths_and_logger", lambda *args: ctx)
    monkeypatch.setattr(mod, "run_mode", lambda run_ctx: {"ok": True, "mode": run_ctx.cli.mode})
    monkeypatch.setattr(mod, "finalize_and_report", lambda run_ctx, result: exit_code)
    monkeypatch.setattr(mod.threading, "Event", _FakeEvent)

    rc = mod.main([])

    assert rc == exit_code
    assert logger.control_events == []
    assert ipc.begin_calls == []
    assert ipc.wait_calls == 0
    assert ipc.stop_calls == 1
    assert waits == [expected_delay]
