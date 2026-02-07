from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path
from typing import Any

# Ensure repository root is importable for 'plugins.*' imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from plugins.web_interface.core import WebInterfacePlugin


def _assert_not_in_repo(repo_root: Path, target: Path) -> None:
    resolved = target.resolve()
    if resolved == repo_root or repo_root in resolved.parents:
        raise AssertionError(f"unexpected repo write: {resolved}")


def _asgi_request(
    app: Any,
    *,
    method: str,
    path: str,
    json_body: dict[str, Any] | None = None,
) -> tuple[int, bytes, dict[str, str]]:
    body: bytes
    headers: list[tuple[bytes, bytes]] = []

    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        headers.append((b"content-type", b"application/json"))
    else:
        body = b""

    scope = {
        "type": "http",
        "asgi": {"spec_version": "2.3", "version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal body
        if body is None:
            return {"type": "http.disconnect"}
        chunk = body
        body = None  # type: ignore[assignment]
        return {"type": "http.request", "body": chunk, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    asyncio.run(app(scope, receive, send))

    status = 500
    resp_headers: dict[str, str] = {}
    body_out = b""
    for msg in messages:
        if msg["type"] == "http.response.start":
            status = int(msg["status"])
            for k, v in msg.get("headers", []):
                resp_headers[k.decode("latin-1").lower()] = v.decode("latin-1")
        elif msg["type"] == "http.response.body":
            body_out += msg.get("body", b"")
    return status, body_out, resp_headers


@pytest.mark.unit
def test_web_interface_does_not_write_to_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Isolate HOME so web writes go to a temp location.
    monkeypatch.setenv("HOME", str(tmp_path))

    repo_root = Path.cwd().resolve()

    orig_write_text = Path.write_text
    orig_write_bytes = Path.write_bytes
    orig_unlink = Path.unlink
    orig_mkdir = Path.mkdir
    orig_rmtree = shutil.rmtree

    def guarded_write_text(self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        _assert_not_in_repo(repo_root, self)
        return orig_write_text(self, *args, **kwargs)

    def guarded_write_bytes(self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        _assert_not_in_repo(repo_root, self)
        return orig_write_bytes(self, *args, **kwargs)

    def guarded_unlink(self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        _assert_not_in_repo(repo_root, self)
        return orig_unlink(self, *args, **kwargs)

    def guarded_mkdir(self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        _assert_not_in_repo(repo_root, self)
        return orig_mkdir(self, *args, **kwargs)

    def guarded_rmtree(path, *args, **kwargs):  # type: ignore[no-untyped-def]
        _assert_not_in_repo(repo_root, Path(path))
        return orig_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", guarded_write_text, raising=True)
    monkeypatch.setattr(Path, "write_bytes", guarded_write_bytes, raising=True)
    monkeypatch.setattr(Path, "unlink", guarded_unlink, raising=True)
    monkeypatch.setattr(Path, "mkdir", guarded_mkdir, raising=True)
    monkeypatch.setattr(shutil, "rmtree", guarded_rmtree, raising=True)

    app = WebInterfacePlugin().create_app()

    # Raw config editor endpoint must not exist.
    status, _, _ = _asgi_request(
        app, method="PUT", path="/api/am/config", json_body={"yaml": "x: 1"}
    )
    assert status in (404, 405)

    inbox = tmp_path / "inbox"

    # Structured config set is allowed (writes under HOME).
    status, body, _ = _asgi_request(
        app,
        method="POST",
        path="/api/am/config/set",
        json_body={"key_path": "inbox_dir", "value": str(inbox)},
    )
    assert status == 200
    assert json.loads(body.decode("utf-8")).get("ok") is True

    # Wizard CRUD goes to user config dir (under HOME).
    status, _, _ = _asgi_request(
        app,
        method="POST",
        path="/api/wizards",
        json_body={"name": "w1", "yaml": "wizard:\n  steps: []\n"},
    )
    assert status == 200

    # Stage listing creates stage dir under inbox/stage (under HOME).
    status, body, _ = _asgi_request(app, method="GET", path="/api/stage")
    assert status == 200
    stage_dir = json.loads(body.decode("utf-8")).get("dir")
    assert stage_dir == str(inbox / "stage")

    # Plugin listing is read-only and must not write to repo.
    status, _, _ = _asgi_request(app, method="GET", path="/api/plugins")
    assert status == 200

    # Enable/disable writes only to user config dir (under HOME).
    status, _, _ = _asgi_request(app, method="POST", path="/api/plugins/example/disable")
    assert status == 200
    status, _, _ = _asgi_request(app, method="POST", path="/api/plugins/example/enable")
    assert status == 200
