"""Import engine PHASE 2 tests.

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


def _make_book(tmp_inbox: Path, rel: str, *, content: bytes) -> None:
    book_dir = tmp_inbox / rel
    book_dir.mkdir(parents=True, exist_ok=True)
    (book_dir / "track01.m4a").write_bytes(content)
    (book_dir / "cover.jpg").write_bytes(b"img")


def _make_preflight(rel: str) -> PreflightResult:
    b = BookPreflight(
        book_ref="book_test",
        unit_type="dir",
        author="A",
        book="B",
        rel_path=rel,
        suggested_author="A",
        suggested_title="B",
        cover_candidates=[f"{rel}/cover.jpg"],
        rename_preview={rel: rel},
        fingerprint=BookFingerprint(algo="sha256", value="x", strength="basic"),
        meta={"id3_majority": None},
    )
    return PreflightResult(source_root_rel_path="", authors=["A"], books=[b], skipped=[])


def _hash_tree(path: Path) -> list[tuple[str, bytes]]:
    files = sorted([p for p in path.rglob("*") if p.is_file()])
    res: list[tuple[str, bytes]] = []
    for p in files:
        res.append((str(p.relative_to(path)), p.read_bytes()))
    return res


def test_import_engine_stage_determinism(tmp_path: Path) -> None:
    fs = _make_fs(tmp_path)
    jobs = _make_job_service(tmp_path)
    engine = ImportEngineService(fs=fs, jobs=jobs)

    rel = "Author/Book"
    _make_book(tmp_path / "inbox", rel, content=b"abc")

    preflight = _make_preflight(rel)
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

    engine.run_pending(limit=10)
    staged1 = _hash_tree(tmp_path / "stage")

    # Run a second time into a fresh stage dir to ensure deterministic output.
    # Reset JOBS root to avoid processed-registry carry-over.
    import shutil

    shutil.rmtree(tmp_path / "jobs")
    (tmp_path / "jobs").mkdir()

    (tmp_path / "stage").rename(tmp_path / "stage1")
    (tmp_path / "stage").mkdir()

    jobs2 = _make_job_service(tmp_path / "j2")
    engine2 = ImportEngineService(fs=fs, jobs=jobs2)
    state2 = ImportRunState(
        source_selection_snapshot={"source": "inbox"}, source_handling_mode="stage"
    )
    decisions2 = engine2.resolve_book_decisions(preflight=preflight, state=state2)
    engine2.start_import_job(
        ImportJobRequest(
            run_id="run2", source_root=RootName.INBOX.value, state=state2, decisions=decisions2
        )
    )
    engine2.run_pending(limit=10)
    staged2 = _hash_tree(tmp_path / "stage")

    assert staged1 == staged2


def test_import_engine_inplace_semantics(tmp_path: Path) -> None:
    fs = _make_fs(tmp_path)
    jobs = _make_job_service(tmp_path)
    engine = ImportEngineService(fs=fs, jobs=jobs)

    rel = "Author/Book"
    _make_book(tmp_path / "inbox", rel, content=b"abc")

    preflight = _make_preflight(rel)
    state = ImportRunState(
        source_selection_snapshot={"source": "inbox"}, source_handling_mode="inplace"
    )
    decisions = engine.resolve_book_decisions(preflight=preflight, state=state)
    engine.start_import_job(
        ImportJobRequest(
            run_id="run1", source_root=RootName.INBOX.value, state=state, decisions=decisions
        )
    )
    engine.run_pending(limit=10)

    # Inplace mode must not write anything into stage.
    assert _hash_tree(tmp_path / "stage") == []


def test_import_engine_retry_behavior(tmp_path: Path) -> None:
    fs = _make_fs(tmp_path)
    jobs = _make_job_service(tmp_path)
    engine = ImportEngineService(fs=fs, jobs=jobs)

    rel = "Author/Book"
    # No book created -> job should fail.
    preflight = _make_preflight(rel)
    state = ImportRunState(
        source_selection_snapshot={"source": "inbox"}, source_handling_mode="stage"
    )
    decisions = engine.resolve_book_decisions(preflight=preflight, state=state)
    engine.start_import_job(
        ImportJobRequest(
            run_id="run1", source_root=RootName.INBOX.value, state=state, decisions=decisions
        )
    )

    engine.run_pending(limit=10)
    failed = [j for j in jobs.list_jobs() if j.state.value == "failed"]
    assert len(failed) == 1

    # Fix source and retry.
    _make_book(tmp_path / "inbox", rel, content=b"abc")
    new_ids = engine.retry_failed_jobs(run_id="run1")
    assert len(new_ids) == 1
    engine.run_pending(limit=10)

    ok = [j for j in jobs.list_jobs() if j.job_id == new_ids[0]][0]
    assert ok.state.value == "succeeded"


def test_import_engine_cli_service_entry(tmp_path: Path) -> None:
    fs = _make_fs(tmp_path)
    jobs = _make_job_service(tmp_path)
    engine = ImportEngineService(fs=fs, jobs=jobs)

    preflight = _make_preflight("Author/Book")
    state = ImportRunState(
        source_selection_snapshot={"source": "inbox"}, source_handling_mode="stage"
    )
    decisions = engine.resolve_book_decisions(preflight=preflight, state=state)

    assert decisions[0].book_rel_path == "Author/Book"
