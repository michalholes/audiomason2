from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def _import_am_patch():
    scripts_dir = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    from am_patch.config import Policy, build_policy
    from am_patch.errors import RunnerError
    from am_patch.log import Logger
    from am_patch.repo_root import resolve_repo_root

    return Logger, Policy, RunnerError, build_policy, resolve_repo_root


def _mk_logger(
    tmp_path: Path,
    *,
    stage: str = "PREFLIGHT",
    json_enabled: bool = False,
):
    logger_cls, *_ = _import_am_patch()
    return logger_cls(
        log_path=tmp_path / "am_patch.log",
        symlink_path=tmp_path / "am_patch.symlink",
        screen_level="quiet",
        log_level="quiet",
        symlink_enabled=False,
        json_enabled=json_enabled,
        json_path=(tmp_path / "am_patch.jsonl") if json_enabled else None,
        stage_provider=lambda: stage,
        run_timeout_s=7,
    )


def test_run_logged_timeout_raises_gate_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logger = _mk_logger(tmp_path, stage="GATE_PYTEST")
    _, _, runner_error_cls, _, _ = _import_am_patch()

    def _boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=kwargs.get("args", args[0] if args else ["python"]),
            timeout=kwargs.get("timeout", 7),
            output="partial stdout\n",
            stderr="partial stderr\n",
        )

    monkeypatch.setattr("am_patch.log.subprocess.run", _boom)

    try:
        with pytest.raises(runner_error_cls) as excinfo:
            logger.run_logged([sys.executable, "-c", "print('x')"])
    finally:
        logger.close()

    assert excinfo.value.stage == "GATES"
    assert excinfo.value.category == "TIMEOUT"
    assert "gate failed: pytest" in excinfo.value.message
    assert "timeout after 7s" in excinfo.value.message


def test_run_logged_timeout_soft_fail_returns_run_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logger = _mk_logger(tmp_path)

    def _boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=kwargs.get("args", args[0] if args else ["python"]),
            timeout=kwargs.get("timeout", 7),
            output="partial stdout\n",
            stderr="partial stderr\n",
        )

    monkeypatch.setattr("am_patch.log.subprocess.run", _boom)

    try:
        res = logger.run_logged([sys.executable, "-c", "print('x')"], timeout_hard_fail=False)
    finally:
        logger.close()

    assert res.returncode == 124
    assert "partial stdout" in res.stdout
    assert "subprocess timeout after 7s" in res.stderr
    assert "partial stderr" in res.stderr


def test_run_logged_emits_json_run_event(tmp_path: Path) -> None:
    logger = _mk_logger(tmp_path, stage="GATE_PYTEST", json_enabled=True)
    try:
        logger.run_logged([sys.executable, "-c", "print('ok')"])
    finally:
        logger.close()

    json_lines = (tmp_path / "am_patch.jsonl").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in json_lines]
    assert any(
        evt.get("type") == "log"
        and evt.get("stage") == "GATE_PYTEST"
        and evt.get("kind") == "RUN"
        and evt.get("msg") == "RUN"
        for evt in events
    )


def test_resolve_repo_root_timeout_falls_back_to_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, _, _, _, resolve_repo_root = _import_am_patch()

    def _boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["git"], timeout=3)

    monkeypatch.setattr("am_patch.repo_root.subprocess.run", _boom)
    monkeypatch.chdir(tmp_path)

    assert resolve_repo_root(timeout_s=3) == tmp_path


def test_build_policy_validates_runner_subprocess_timeout() -> None:
    _, policy_cls, runner_error_cls, build_policy, _ = _import_am_patch()
    defaults = policy_cls()

    policy = build_policy(defaults, {"runner_subprocess_timeout_s": 0})
    assert policy.runner_subprocess_timeout_s == 0

    policy = build_policy(defaults, {"runner_subprocess_timeout_s": 45})
    assert policy.runner_subprocess_timeout_s == 45

    with pytest.raises(runner_error_cls) as excinfo:
        build_policy(defaults, {"runner_subprocess_timeout_s": -1})

    assert excinfo.value.stage == "CONFIG"
    assert excinfo.value.category == "INVALID"
    assert excinfo.value.message == "runner_subprocess_timeout_s must be >= 0"
