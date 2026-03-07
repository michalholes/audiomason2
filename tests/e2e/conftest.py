from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _wait_until_ready(base_url: str, *, timeout_s: float = 30.0) -> None:
    deadline = time.time() + timeout_s
    health_url = f"{base_url}/api/health"
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=2.0) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last_error = exc
            time.sleep(0.25)

    raise RuntimeError(f"Timed out waiting for {health_url!r}. Last error: {last_error!r}")


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@pytest.fixture(scope="session")
def e2e_base_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    existing = os.getenv("E2E_BASE_URL")
    if existing:
        yield existing.rstrip("/")
        return

    host = os.getenv("E2E_HOST", "127.0.0.1")
    port = int(os.getenv("E2E_PORT", "0")) or _pick_free_port()
    base_url = f"http://{host}:{port}"

    log_dir = tmp_path_factory.mktemp("playwright-e2e")
    log_path = log_dir / "web_interface.log"
    log_file = log_path.open("wb")

    env = os.environ.copy()
    pythonpath = [str(REPO_ROOT), str(REPO_ROOT / "src")]
    existing_pythonpath = env.get("PYTHONPATH")
    if existing_pythonpath:
        pythonpath.append(existing_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(pythonpath)
    env["E2E_HOST"] = host
    env["E2E_PORT"] = str(port)
    env.setdefault("E2E_WEB_VERBOSITY", "0")

    process = subprocess.Popen(
        [sys.executable, str(REPO_ROOT / "tests" / "e2e" / "_server.py")],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )

    try:
        _wait_until_ready(base_url)
    except Exception as err:
        _terminate_process(process)
        log_file.flush()
        startup_log = log_path.read_text(encoding="utf-8", errors="replace")
        raise RuntimeError(
            f"Failed to start the e2e web server. See captured log at {log_path}:\n{startup_log}"
        ) from err

    try:
        yield base_url
    finally:
        _terminate_process(process)
        log_file.close()
