from __future__ import annotations

import io
import json
import os
import zipfile
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from plugins.web_interface.api.ui_schema import mount_ui_schema

from audiomason.core.config import ConfigResolver


@dataclass
class _Manifest:
    name: str
    version: str
    description: str = ""
    author: str = ""
    license: str = ""


class _DummyPluginLoader:
    def __init__(self) -> None:
        self._names = ["web_interface", "file_io"]
        self._man = {
            "web_interface": _Manifest(name="web_interface", version="0.1.0"),
            "file_io": _Manifest(name="file_io", version="0.1.0"),
        }

    def list_plugins(self) -> list[str]:
        return list(self._names)

    def get_manifest(self, name: str) -> _Manifest:
        return self._man[name]


def _write(path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_debug_bundle_zip_contents_and_redaction(tmp_path) -> None:
    pytest.importorskip("httpx")

    from fastapi.testclient import TestClient

    cfg_dir = tmp_path / "cfg"
    inbox_dir = tmp_path / "inbox"
    stage_dir = tmp_path / "stage"
    jobs_dir = tmp_path / "jobs"
    outbox_dir = tmp_path / "outbox"
    wiz_dir = tmp_path / "wizards"

    # files that will be bundled
    _write(cfg_dir / "web_interface_ui.json", json.dumps({"api_token": "SECRET", "x": 1}))
    _write(outbox_dir / "logs/system.log", "a\nB\nC\n")
    _write(stage_dir / "diagnostics/diagnostics.jsonl", '{"event":"x"}\n{"event":"y"}\n')

    j1 = jobs_dir / "job_00000128.json"
    j2 = jobs_dir / "job_00000129.json"
    _write(j1, '{"id":128}\n')
    _write(j2, '{"id":129}\n')
    _write(j2.with_suffix(".log"), "joblog\n")

    # make j2 newer
    os.utime(j1, (1, 1))
    os.utime(j2, (2, 2))
    os.utime(j2.with_suffix(".log"), (2, 2))

    defaults = {
        "file_io": {
            "roots": {
                "config_dir": str(cfg_dir),
                "inbox_dir": str(inbox_dir),
                "stage_dir": str(stage_dir),
                "jobs_dir": str(jobs_dir),
                "outbox_dir": str(outbox_dir),
                "wizards_dir": str(wiz_dir),
            }
        },
        "logging": {"system_log_path": str(outbox_dir / "logs/system.log")},
        "api_token": "SECRET_VALUE",
        "output_dir": str(outbox_dir),
    }

    resolver = ConfigResolver(defaults=defaults)

    app = FastAPI()
    app.state.config_resolver = resolver
    app.state.plugin_loader = _DummyPluginLoader()
    mount_ui_schema(app)

    c = TestClient(app)
    r = c.get("/api/debug/bundle?logs_tail_lines=2&jobs_n=1")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/zip")

    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(z.namelist())
    assert "debug_bundle/meta.json" in names
    assert "debug_bundle/config/effective_config.json" in names
    assert "debug_bundle/plugins/plugins.json" in names
    assert "debug_bundle/ui/ui_overrides.json" in names
    assert "debug_bundle/logs/system.log.tail" in names
    assert "debug_bundle/logs/diagnostics.jsonl.tail" in names
    # newest job selected
    assert "debug_bundle/jobs/job_00000129.json" in names
    assert "debug_bundle/jobs/job_00000129.log" in names

    cfg = json.loads(z.read("debug_bundle/config/effective_config.json").decode("utf-8"))
    assert cfg.get("api_token") == "***REDACTED***"

    ui = json.loads(z.read("debug_bundle/ui/ui_overrides.json").decode("utf-8"))
    assert ui.get("api_token") == "***REDACTED***"
