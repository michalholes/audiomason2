"""Unit tests for import.processed_registry."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

ProcessedRegistry = importlib.import_module(
    "plugins.import.processed_registry.service"
).ProcessedRegistry


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


def test_processed_registry_round_trip(service: FileService) -> None:
    reg = ProcessedRegistry(service)

    book = "Author/Book"
    assert reg.is_processed(book) is False

    reg.mark_processed(book)
    assert reg.is_processed(book) is True
    assert reg.stats().count == 1

    reg.unmark_processed(book)
    assert reg.is_processed(book) is False
    assert reg.stats().count == 0
