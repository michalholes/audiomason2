from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def _make_minimal_inbox(inbox: Path) -> None:
    (inbox / "Author" / "Book").mkdir(parents=True)
    # Minimal marker file (content not used by preflight discovery).
    (inbox / "Author" / "Book" / "track01.mp3").write_bytes(b"")


def test_import_cli_prints_preflight_boundary_in_debug(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    inbox = tmp_path / "inbox"
    stage = tmp_path / "stage"
    outbox = tmp_path / "outbox"

    _make_minimal_inbox(inbox)

    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_INBOX_DIR", str(inbox))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_STAGE_DIR", str(stage))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_OUTBOX_DIR", str(outbox))
    monkeypatch.setenv("HOME", str(tmp_path))

    # import_cli reads sys.argv to detect -d/--debug.
    monkeypatch.setattr(sys, "argv", ["audiomason", "-d", "import"], raising=False)

    from plugins.import_cli.plugin import ImportCLIPlugin

    plugin = ImportCLIPlugin()

    plugin.import_cmd(
        [
            "--root",
            "inbox",
            "--path",
            ".",
            "--mode",
            "stage",
            "--non-interactive",
            "--all",
        ]
    )

    out = capsys.readouterr().out
    assert "DIAG boundary.start" in out
    assert "operation=preflight" in out
    assert "DIAG boundary.end" in out


def test_import_cli_diagnostics_reach_syslog_when_enabled(tmp_path: Path, monkeypatch: Any) -> None:
    inbox = tmp_path / "inbox"
    stage = tmp_path / "stage"
    outbox = tmp_path / "outbox"
    cfg_root = tmp_path / "config_root"

    _make_minimal_inbox(inbox)

    # syslog plugin reads resolver defaults via HOME config.
    monkeypatch.setenv("HOME", str(tmp_path))

    cfg_path = tmp_path / ".config" / "audiomason" / "config.yaml"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(
        f"""
logging:
  level: debug
  system_log_enabled: true
  system_log_path: logs/system.log
file_io:
  roots:
    inbox_dir: {str(inbox)}
    stage_dir: {str(stage)}
    outbox_dir: {str(outbox)}
    config_dir: {str(cfg_root)}
diagnostics:
  enabled: true
""",
        encoding="utf-8",
    )

    # Enable syslog sink.
    from plugins.syslog.plugin import SyslogPlugin

    _syslog = SyslogPlugin()

    # import_cli reads sys.argv to detect -d/--debug.
    monkeypatch.setattr(sys, "argv", ["audiomason", "-d", "import"], raising=False)

    from plugins.import_cli.plugin import ImportCLIPlugin

    plugin = ImportCLIPlugin()
    plugin.import_cmd(
        [
            "--root",
            "inbox",
            "--path",
            ".",
            "--mode",
            "stage",
            "--non-interactive",
            "--all",
        ]
    )

    syslog_path = stage / "logs" / "system.log"
    raw = syslog_path.read_text(encoding="utf-8", errors="replace")

    # The syslog sink stores LogBus records; import_cli emits a debug log line
    # containing the serialized diagnostics envelope prefixed by "DIAG ".
    assert "DIAG" in raw
    assert 'component\\":\\"import_cli' in raw
    assert 'event\\":\\"boundary.start' in raw
