"""Unit tests for import.preflight determinism."""

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


def test_preflight_is_deterministic(service: FileService) -> None:
    # Arrange: inbox/source/Author/Book with files.
    service.mkdir(RootName.INBOX, "source/Author", parents=True, exist_ok=True)
    service.mkdir(RootName.INBOX, "source/Author/Book", parents=True, exist_ok=True)

    _write(service, RootName.INBOX, "source/Author/Book/01.m4a", b"audio1")
    _write(service, RootName.INBOX, "source/Author/Book/02.m4a", b"audio2")
    _write(service, RootName.INBOX, "source/Author/Book/cover.jpg", b"img")

    svc = PreflightService(service)

    r1 = svc.run(RootName.INBOX, "source")
    r2 = svc.run(RootName.INBOX, "source")

    assert r1 == r2
    assert r1.authors == ["Author"]
    assert len(r1.books) == 1
    assert r1.skipped == []
    assert r1.books[0].book_ref.startswith("book_")
    assert r1.books[0].unit_type == "dir"
    assert r1.books[0].fingerprint is not None
    assert r1.books[0].cover_candidates == ["source/Author/Book/cover.jpg"]
