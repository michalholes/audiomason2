"""Import job handler file-source support.

ASCII-only.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

from audiomason.core.jobs.api import JobService
from audiomason.core.jobs.store import JobStore

ImportJobRequest = importlib.import_module("plugins.import.engine.types").ImportJobRequest
PreflightTypes = importlib.import_module("plugins.import.preflight.types")
BookFingerprint = PreflightTypes.BookFingerprint
BookPreflight = PreflightTypes.BookPreflight
PreflightResult = PreflightTypes.PreflightResult
ImportEngineService = importlib.import_module("plugins.import.services").ImportEngineService
ImportRunState = importlib.import_module("plugins.import.session_store.types").ImportRunState


def _make_fs(tmp_path: Path) -> FileService:
    inbox = tmp_path / "inbox"
    stage = tmp_path / "stage"
    jobs = tmp_path / "jobs"
    outbox = tmp_path / "outbox"
    inbox.mkdir()
    stage.mkdir()
    jobs.mkdir()
    outbox.mkdir()
    return FileService(
        {
            RootName.INBOX: inbox,
            RootName.STAGE: stage,
            RootName.JOBS: jobs,
            RootName.OUTBOX: outbox,
        }
    )


def _make_job_service(tmp_path: Path) -> JobService:
    store = JobStore(root=tmp_path / "job_store")
    return JobService(store=store)


def _make_preflight_file(rel: str) -> PreflightResult:
    b = BookPreflight(
        book_ref="file_unit",
        unit_type="file",
        author="A",
        book="B",
        rel_path=rel,
        suggested_author="A",
        suggested_title="B",
        cover_candidates=None,
        rename_preview={rel: rel},
        fingerprint=BookFingerprint(algo="sha256", value="x", strength="basic"),
        meta=None,
    )
    return PreflightResult(source_root_rel_path="", authors=["A"], books=[b], skipped=[])


def _hash_tree(path: Path) -> list[str]:
    files = sorted([p for p in path.rglob("*") if p.is_file()])
    return [str(p.relative_to(path)) for p in files]


def test_stage_mode_stages_single_audio_file(tmp_path: Path) -> None:
    fs = _make_fs(tmp_path)
    jobs = _make_job_service(tmp_path)
    engine = ImportEngineService(fs=fs, jobs=jobs)

    (tmp_path / "inbox" / "book.mp3").write_bytes(b"abc")

    preflight = _make_preflight_file("book.mp3")
    state = ImportRunState(
        source_selection_snapshot={"source": "inbox"}, source_handling_mode="stage"
    )
    decisions = engine.resolve_book_decisions(preflight=preflight, state=state)
    job_ids = engine.start_import_job(
        ImportJobRequest(
            run_id="run1", source_root=RootName.INBOX.value, state=state, decisions=decisions
        )
    )
    assert len(job_ids) == 1
    job_id = job_ids[0]

    engine.run_pending(limit=10)

    expected = f"import/stage/{job_id}/book/book.mp3"
    assert expected in _hash_tree(tmp_path / "stage")
    assert [j for j in jobs.list_jobs() if j.job_id == job_id][0].state.value == "succeeded"


def test_stage_mode_stages_archive_file(tmp_path: Path) -> None:
    fs = _make_fs(tmp_path)
    jobs = _make_job_service(tmp_path)
    engine = ImportEngineService(fs=fs, jobs=jobs)

    (tmp_path / "inbox" / "sp.rar").write_bytes(b"rar")

    preflight = _make_preflight_file("sp.rar")
    state = ImportRunState(
        source_selection_snapshot={"source": "inbox"}, source_handling_mode="stage"
    )
    decisions = engine.resolve_book_decisions(preflight=preflight, state=state)
    job_ids = engine.start_import_job(
        ImportJobRequest(
            run_id="run1", source_root=RootName.INBOX.value, state=state, decisions=decisions
        )
    )
    assert len(job_ids) == 1
    job_id = job_ids[0]

    engine.run_pending(limit=10)

    expected = f"import/stage/{job_id}/sp/sp.rar"
    assert expected in _hash_tree(tmp_path / "stage")
    assert [j for j in jobs.list_jobs() if j.job_id == job_id][0].state.value == "succeeded"


def test_inplace_mode_accepts_file_source(tmp_path: Path) -> None:
    fs = _make_fs(tmp_path)
    jobs = _make_job_service(tmp_path)
    engine = ImportEngineService(fs=fs, jobs=jobs)

    (tmp_path / "inbox" / "book.mp3").write_bytes(b"abc")

    preflight = _make_preflight_file("book.mp3")
    state = ImportRunState(
        source_selection_snapshot={"source": "inbox"}, source_handling_mode="inplace"
    )
    decisions = engine.resolve_book_decisions(preflight=preflight, state=state)
    job_ids = engine.start_import_job(
        ImportJobRequest(
            run_id="run1", source_root=RootName.INBOX.value, state=state, decisions=decisions
        )
    )
    assert len(job_ids) == 1
    job_id = job_ids[0]

    engine.run_pending(limit=10)

    assert _hash_tree(tmp_path / "stage") == []
    assert [j for j in jobs.list_jobs() if j.job_id == job_id][0].state.value == "succeeded"
