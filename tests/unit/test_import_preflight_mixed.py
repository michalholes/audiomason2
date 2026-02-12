"""Unit tests for mixed inbox import.preflight discovery."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

PreflightService = importlib.import_module("plugins.import.preflight.service").PreflightService


@pytest.fixture()
def service(tmp_path: Path) -> FileService:
    roots = {
        RootName.INBOX: tmp_path / "inbox",
        RootName.STAGE: tmp_path / "stage",
        RootName.JOBS: tmp_path / "jobs",
        RootName.OUTBOX: tmp_path / "outbox",
        RootName.CONFIG: tmp_path / "config",
        RootName.WIZARDS: tmp_path / "wizards",
    }
    for p in roots.values():
        p.mkdir(parents=True, exist_ok=True)
    return FileService(roots)


def _write(service: FileService, root: RootName, rel: str, data: bytes) -> None:
    with service.open_write(root, rel, overwrite=True, mkdir_parents=True) as f:
        f.write(data)


def test_preflight_discovers_mixed_layout(service: FileService) -> None:
    # Layout:
    # - source/AuthorA/Book1 (dir book)
    # - source/BookSolo (single-level book dir)
    # - source/BookArchive.zip (file unit)
    # - source/Loose.m4a (file unit)
    # - source/notes.txt (skipped)
    service.mkdir(RootName.INBOX, "source/AuthorA/Book1", parents=True, exist_ok=True)
    _write(service, RootName.INBOX, "source/AuthorA/Book1/01.m4a", b"a")

    service.mkdir(RootName.INBOX, "source/BookSolo", parents=True, exist_ok=True)
    _write(service, RootName.INBOX, "source/BookSolo/01.m4a", b"b")

    _write(service, RootName.INBOX, "source/BookArchive.zip", b"zipdata")
    _write(service, RootName.INBOX, "source/Loose.m4a", b"looseaudio")
    _write(service, RootName.INBOX, "source/notes.txt", b"notes")

    svc = PreflightService(service)
    res = svc.run(RootName.INBOX, "source")

    assert res.authors == ["AuthorA"]
    # Deterministic ordering: sort by (author, book, rel_path).
    assert [b.unit_type for b in res.books] == ["file", "dir", "file", "dir"]

    # Author/book discovery
    b_author = [b for b in res.books if b.author == "AuthorA"][0]
    assert b_author.book == "Book1"
    assert b_author.rel_path == "source/AuthorA/Book1"

    # Single-level book directory
    b_solo = [b for b in res.books if b.rel_path == "source/BookSolo"][0]
    assert b_solo.author == ""
    assert b_solo.book == "BookSolo"

    # Single-file units
    b_zip = [b for b in res.books if b.rel_path == "source/BookArchive.zip"][0]
    assert b_zip.book == "BookArchive"

    b_loose = [b for b in res.books if b.rel_path == "source/Loose.m4a"][0]
    assert b_loose.book == "Loose"

    # Skipped entries with reason
    assert len(res.skipped) == 1
    assert res.skipped[0].rel_path == "source/notes.txt"
    assert res.skipped[0].entry_type == "file"
    assert res.skipped[0].reason == "unsupported_file_ext"

    # Stable per-unit book_ref
    assert all(b.book_ref.startswith("book_") for b in res.books)
