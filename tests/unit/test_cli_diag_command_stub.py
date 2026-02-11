"""Unit tests for diagnostics_console CLI command.

These tests are intentionally narrow and rely on monkeypatching to avoid
filesystem I/O.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest


def test_help_lists_diag_command_with_origin(tmp_path: Path) -> None:
    from plugins.cli.plugin import CLIPlugin

    pdir = tmp_path / "diagnostics_console"
    pdir.mkdir(parents=True, exist_ok=True)

    (pdir / "plugin.yaml").write_text(
        "\n".join(
            [
                "name: diagnostics_console",
                'version: "0.0.1"',
                "description: test plugin",
                "author: test",
                "license: MIT",
                'entrypoint: "plugin:Dummy"',
                "interfaces:",
                "  - ICLICommands",
                "cli_commands:",
                "  - diag",
                "hooks: []",
                "dependencies: {}",
                "config_schema: {}",
                'test_level: "none"',
                "",
            ]
        )
    )

    help_text = CLIPlugin._build_help_for_tests([pdir])
    assert "diag    (plugin: diagnostics_console)" in help_text


def test_diag_on_off_calls_configservice(monkeypatch: pytest.MonkeyPatch) -> None:
    from plugins.diagnostics_console.plugin import DiagnosticsConsolePlugin

    calls: list[tuple[str, str, object]] = []

    class FakeConfigService:
        def set_value(self, key_path: str, value: object) -> None:
            calls.append(("set", key_path, value))

        def unset_value(self, key_path: str) -> None:
            calls.append(("unset", key_path, None))

    monkeypatch.setattr("plugins.diagnostics_console.plugin.ConfigService", FakeConfigService)

    plugin = DiagnosticsConsolePlugin()
    diag = plugin.get_cli_commands()["diag"]

    diag(["on"])
    diag(["off"])

    assert calls == [
        ("set", "diagnostics.enabled", True),
        ("unset", "diagnostics.enabled", None),
    ]


def test_diag_tail_no_follow_formats_events(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from plugins.diagnostics_console.plugin import DiagnosticsConsolePlugin

    class FakeFileService:
        def __init__(self) -> None:
            self._data = (
                b'{"event":"diag.job.start","component":"orchestration","operation":"run_job","timestamp":"2026-02-11T12:00:00Z","data":{"job_id":"J1","status":"running"}}\n'
                b"not-json\n"
                b'{"event":"diag.job.end","component":"orchestration","operation":"run_job","timestamp":"2026-02-11T12:00:01Z","data":{"job_id":"J1","status":"succeeded"}}\n'
            )

        @classmethod
        def from_resolver(cls, resolver):  # type: ignore[no-untyped-def]
            return cls()

        def exists(self, root, rel_path: str) -> bool:  # type: ignore[no-untyped-def]
            _ = root
            return rel_path == "diagnostics/diagnostics.jsonl"

        def open_read(self, root, rel_path: str):  # type: ignore[no-untyped-def]
            _ = root
            assert rel_path == "diagnostics/diagnostics.jsonl"
            return _FakeCtx(io.BytesIO(self._data))

    class _FakeCtx:
        def __init__(self, bio: io.BytesIO) -> None:
            self._bio = bio

        def __enter__(self) -> io.BytesIO:
            return self._bio

        def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
            return None

    monkeypatch.setattr("plugins.diagnostics_console.plugin.FileService", FakeFileService)

    # Avoid reading real user/system config in tests.
    class FakeResolver:
        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            pass

        def resolve(self, key: str):  # type: ignore[no-untyped-def]
            raise Exception(key)

    monkeypatch.setattr("plugins.diagnostics_console.plugin.ConfigResolver", FakeResolver)

    plugin = DiagnosticsConsolePlugin()
    diag = plugin.get_cli_commands()["diag"]

    diag(["tail", "--no-follow", "--max-events", "10"])

    out = capsys.readouterr().out.splitlines()

    # Two valid events + one warning for invalid JSON.
    assert any("diag.job.start" in line for line in out)
    assert any("diag.job.end" in line for line in out)
    assert any(line.startswith("WARN:") for line in out)
