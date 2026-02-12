"""Unit tests for import_cli mixed layout support."""

from __future__ import annotations

from pathlib import Path

import pytest


def _set_roots_env(
    monkeypatch: pytest.MonkeyPatch, *, inbox: Path, stage: Path, jobs: Path, outbox: Path
) -> None:
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_INBOX_DIR", str(inbox))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_STAGE_DIR", str(stage))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_JOBS_DIR", str(jobs))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_OUTBOX_DIR", str(outbox))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_CONFIG_DIR", str(outbox / "config"))
    monkeypatch.setenv("AUDIOMASON_FILE_IO_ROOTS_WIZARDS_DIR", str(outbox / "wizards"))


def _write(path: Path, data: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def test_import_cli_non_interactive_all_on_mixed_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from plugins.import_cli.plugin import ImportCLIPlugin

    inbox = tmp_path / "inbox"
    stage = tmp_path / "stage"
    jobs = tmp_path / "jobs"
    outbox = tmp_path / "outbox"
    for p in (inbox, stage, jobs, outbox):
        p.mkdir(parents=True, exist_ok=True)

    _set_roots_env(monkeypatch, inbox=inbox, stage=stage, jobs=jobs, outbox=outbox)

    # Mixed layout under source.
    _write(inbox / "source" / "AuthorA" / "Book1" / "01.m4a", b"a")
    _write(inbox / "source" / "BookSolo" / "01.m4a", b"b")
    _write(inbox / "source" / "Loose.m4a", b"c")

    cli = ImportCLIPlugin()
    cli.import_cmd(
        [
            "--root",
            "inbox",
            "--path",
            "source",
            "--non-interactive",
            "--all",
            "--yes",
            "--parallelism",
            "1",
        ]
    )

    out = capsys.readouterr().out
    assert "Created import run:" in out
    assert "Jobs:" in out


def test_import_cli_interactive_book_only_layout_prompts_for_book(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from plugins.import_cli.plugin import ImportCLIPlugin

    inbox = tmp_path / "inbox"
    stage = tmp_path / "stage"
    jobs = tmp_path / "jobs"
    outbox = tmp_path / "outbox"
    for p in (inbox, stage, jobs, outbox):
        p.mkdir(parents=True, exist_ok=True)

    _set_roots_env(monkeypatch, inbox=inbox, stage=stage, jobs=jobs, outbox=outbox)

    # Book-only layout: source/BookSolo.
    _write(inbox / "source" / "BookSolo" / "01.m4a", b"b")

    inputs = iter(["1"])  # select the only discovered book

    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))

    cli = ImportCLIPlugin()
    cli.import_cmd(["--root", "inbox", "--path", "source", "--parallelism", "1"])

    out = capsys.readouterr().out
    assert "Select book" in out
    assert "Created import run:" in out


def test_import_cli_interactive_mixed_layout_includes_book_only_bucket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from plugins.import_cli.plugin import ImportCLIPlugin

    inbox = tmp_path / "inbox"
    stage = tmp_path / "stage"
    jobs = tmp_path / "jobs"
    outbox = tmp_path / "outbox"
    for p in (inbox, stage, jobs, outbox):
        p.mkdir(parents=True, exist_ok=True)

    _set_roots_env(monkeypatch, inbox=inbox, stage=stage, jobs=jobs, outbox=outbox)

    # Mixed layout: one author dir and one book-only dir.
    _write(inbox / "source" / "AuthorA" / "Book1" / "01.m4a", b"a")
    _write(inbox / "source" / "BookSolo" / "01.m4a", b"b")

    # Author options should include AuthorA and <book-only>.
    # Select <book-only> (2), then select BookSolo (1).
    inputs = iter(["2", "1"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(inputs))

    cli = ImportCLIPlugin()
    cli.import_cmd(["--root", "inbox", "--path", "source", "--parallelism", "1"])

    out = capsys.readouterr().out
    assert "<book-only>" in out
    assert "Created import run:" in out
