"""Unit tests for file_io FileService."""

from __future__ import annotations

from pathlib import Path

import pytest
from plugins.file_io.service import FileService, RootName
from plugins.file_io.service.ops import AlreadyExistsError, IsADirectoryError, NotFoundError


@pytest.fixture()
def service(tmp_path: Path) -> FileService:
    roots = {
        RootName.INBOX: tmp_path / "inbox",
        RootName.STAGE: tmp_path / "stage",
        RootName.JOBS: tmp_path / "jobs",
        RootName.OUTBOX: tmp_path / "outbox",
    }
    for p in roots.values():
        p.mkdir(parents=True, exist_ok=True)
    return FileService(roots)


def test_mkdir_and_list_dir_stable_order(service: FileService) -> None:
    service.mkdir(RootName.INBOX, "b")
    service.mkdir(RootName.INBOX, "a")
    entries = service.list_dir(RootName.INBOX, ".")
    assert [e.rel_path for e in entries] == ["a", "b"]


def test_exists_stat_and_open_roundtrip(service: FileService) -> None:
    with service.open_write(RootName.INBOX, "hello.bin") as f:
        f.write(b"hello")

    assert service.exists(RootName.INBOX, "hello.bin")
    st = service.stat(RootName.INBOX, "hello.bin")
    assert st.size == 5
    assert not st.is_dir

    with service.open_read(RootName.INBOX, "hello.bin") as f:
        assert f.read() == b"hello"


def test_delete_and_not_found(service: FileService) -> None:
    with service.open_write(RootName.INBOX, "x.bin") as f:
        f.write(b"x")
    service.delete_file(RootName.INBOX, "x.bin")
    assert not service.exists(RootName.INBOX, "x.bin")

    with pytest.raises(NotFoundError):
        service.delete_file(RootName.INBOX, "x.bin")


def test_rmdir_and_rmtree(service: FileService) -> None:
    service.mkdir(RootName.INBOX, "d")
    service.rmdir(RootName.INBOX, "d")

    service.mkdir(RootName.INBOX, "tree/sub")
    with service.open_write(RootName.INBOX, "tree/sub/f.bin") as f:
        f.write(b"y")

    service.rmtree(RootName.INBOX, "tree")
    assert not service.exists(RootName.INBOX, "tree")


def test_rename_and_overwrite(service: FileService) -> None:
    with service.open_write(RootName.INBOX, "a.bin") as f:
        f.write(b"a")

    service.rename(RootName.INBOX, "a.bin", "b.bin")
    assert service.exists(RootName.INBOX, "b.bin")
    assert not service.exists(RootName.INBOX, "a.bin")

    with service.open_write(RootName.INBOX, "c.bin") as f:
        f.write(b"c")

    with pytest.raises(AlreadyExistsError):
        service.rename(RootName.INBOX, "b.bin", "c.bin", overwrite=False)

    service.rename(RootName.INBOX, "b.bin", "c.bin", overwrite=True)
    assert service.exists(RootName.INBOX, "c.bin")


def test_copy_and_checksum(service: FileService) -> None:
    with service.open_write(RootName.INBOX, "src.bin") as f:
        f.write(b"data")

    service.copy(RootName.INBOX, "src.bin", "dst.bin")
    with service.open_read(RootName.INBOX, "dst.bin") as f:
        assert f.read() == b"data"

    cs1 = service.checksum(RootName.INBOX, "src.bin")
    cs2 = service.checksum(RootName.INBOX, "dst.bin")
    assert cs1 == cs2

    service.mkdir(RootName.INBOX, "dir")
    with pytest.raises(IsADirectoryError):
        service.checksum(RootName.INBOX, "dir")
