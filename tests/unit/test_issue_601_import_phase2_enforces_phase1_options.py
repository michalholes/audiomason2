"""Issue 601 regression tests.

PHASE 2 must strictly enforce PHASE 1 options.

ASCII-only.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

from audiomason.core.jobs.api import JobService
from audiomason.core.jobs.model import JobState, JobType
from audiomason.core.jobs.store import JobStore

import_job = importlib.import_module("plugins.import.job_handlers.import_job")
ProcessedRegistry = importlib.import_module(
    "plugins.import.processed_registry.service"
).ProcessedRegistry
ImportRunState = importlib.import_module("plugins.import.session_store.types").ImportRunState


def _mk_services(tmp_path: Path) -> tuple[FileService, JobService, ProcessedRegistry]:
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

    fs = FileService(roots=roots)
    job_service = JobService(store=JobStore(root=tmp_path / "job_store"))
    registry = ProcessedRegistry(fs)
    return fs, job_service, registry


def _mk_running_job(job_service: JobService, *, unit_type: str) -> str:
    job = job_service.create_job(JobType.PROCESS, meta={"unit_type": unit_type})
    job.state = JobState.RUNNING
    job_service.store.save_job(job)
    return job.job_id


def test_audio_processing_requires_enabled_and_confirmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fs, job_service, registry = _mk_services(tmp_path)

    src = tmp_path / "inbox" / "book.mp3"
    src.write_bytes(b"src")

    # If PHASE 2 incorrectly treats truthy values as enabled/confirmed,
    # this would run ffmpeg. Enforce that it does NOT run.
    def _boom(*args, **kwargs):
        raise AssertionError("ffmpeg subprocess should not be called")

    monkeypatch.setattr(import_job.subprocess, "run", _boom)

    job_id = _mk_running_job(job_service, unit_type="file")

    state = ImportRunState(
        source_selection_snapshot={},
        source_handling_mode="inplace",
        global_options={
            "conflict_policy": "overwrite",
            "audio_processing": {"enabled": True, "confirmed": False, "bitrate_kbps": 96},
        },
    )

    import_job.run_import_job(
        job_id=job_id,
        job_service=job_service,
        fs=fs,
        registry=registry,
        run_state=state,
        source_root=RootName.INBOX,
        book_rel_path="book.mp3",
    )

    job = job_service.get_job(job_id)
    assert job.state == JobState.SUCCEEDED


def test_audio_processing_runs_only_when_confirmed_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fs, job_service, registry = _mk_services(tmp_path)

    src = tmp_path / "inbox" / "book.mp3"
    src.write_bytes(b"src")

    def _fake_run(cmd, capture_output, text):
        # last arg is output path
        out = Path(cmd[-1])
        out.write_bytes(b"encoded")

        class _Res:
            returncode = 0
            stderr = ""
            stdout = ""

        return _Res()

    monkeypatch.setattr(import_job.subprocess, "run", _fake_run)

    job_id = _mk_running_job(job_service, unit_type="file")

    state = ImportRunState(
        source_selection_snapshot={},
        source_handling_mode="inplace",
        global_options={
            "conflict_policy": "overwrite",
            "audio_processing": {"enabled": True, "confirmed": True, "bitrate_kbps": 96},
        },
    )

    import_job.run_import_job(
        job_id=job_id,
        job_service=job_service,
        fs=fs,
        registry=registry,
        run_state=state,
        source_root=RootName.INBOX,
        book_rel_path="book.mp3",
    )

    assert src.read_bytes() == b"encoded"
    job = job_service.get_job(job_id)
    assert job.state == JobState.SUCCEEDED


def test_delete_source_guard_toggle_is_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fs, job_service, registry = _mk_services(tmp_path)

    (tmp_path / "inbox" / "book").mkdir(parents=True, exist_ok=True)
    (tmp_path / "inbox" / "book" / "a.mp3").write_bytes(b"src")

    job_id = _mk_running_job(job_service, unit_type="dir")

    # Force a fingerprint mismatch across the two calls in PHASE 2.
    calls = {"n": 0}

    def _fake_fp(*args, **kwargs):
        calls["n"] += 1
        return "k1" if calls["n"] == 1 else "k2"

    monkeypatch.setattr(import_job, "build_book_fingerprint_key", _fake_fp)

    state_guard_on = ImportRunState(
        source_selection_snapshot={},
        source_handling_mode="stage",
        global_options={
            "conflict_policy": "overwrite",
            "delete_source": {"enabled": True, "guard_enabled": True},
        },
    )

    import_job.run_import_job(
        job_id=job_id,
        job_service=job_service,
        fs=fs,
        registry=registry,
        run_state=state_guard_on,
        source_root=RootName.INBOX,
        book_rel_path="book",
    )

    assert (tmp_path / "inbox" / "book").exists(), "guard should prevent deletion on mismatch"

    # Fresh job for guard disabled run.
    job_id2 = _mk_running_job(job_service, unit_type="dir")
    calls["n"] = 0

    # Use a different identity key so the processed registry does not short-circuit PHASE 2.
    def _fake_fp2(*args, **kwargs):
        calls["n"] += 1
        return "k3" if calls["n"] == 1 else "k4"

    monkeypatch.setattr(import_job, "build_book_fingerprint_key", _fake_fp2)

    state_guard_off = ImportRunState(
        source_selection_snapshot={},
        source_handling_mode="stage",
        global_options={
            "conflict_policy": "overwrite",
            "delete_source": {"enabled": True, "guard_enabled": False},
        },
    )

    import_job.run_import_job(
        job_id=job_id2,
        job_service=job_service,
        fs=fs,
        registry=registry,
        run_state=state_guard_off,
        source_root=RootName.INBOX,
        book_rel_path="book",
    )

    assert not (tmp_path / "inbox" / "book").exists(), (
        "guard disabled should delete deterministically"
    )


def test_invalid_conflict_policy_fails_deterministically(tmp_path: Path) -> None:
    fs, job_service, registry = _mk_services(tmp_path)

    (tmp_path / "inbox" / "book").mkdir(parents=True, exist_ok=True)
    (tmp_path / "inbox" / "book" / "a.mp3").write_bytes(b"src")

    job_id = _mk_running_job(job_service, unit_type="dir")

    state = ImportRunState(
        source_selection_snapshot={},
        source_handling_mode="stage",
        global_options={
            "conflict_policy": "not-a-policy",
        },
    )

    import_job.run_import_job(
        job_id=job_id,
        job_service=job_service,
        fs=fs,
        registry=registry,
        run_state=state,
        source_root=RootName.INBOX,
        book_rel_path="book",
    )

    job = job_service.get_job(job_id)
    assert job.state == JobState.FAILED
    assert job.error is not None
    assert "Invalid conflict_policy" in job.error


def test_conflict_policy_skip_does_not_overwrite_existing_stage_files(tmp_path: Path) -> None:
    fs, job_service, registry = _mk_services(tmp_path)

    (tmp_path / "inbox" / "book").mkdir(parents=True, exist_ok=True)
    (tmp_path / "inbox" / "book" / "a.mp3").write_bytes(b"new")

    job_id = _mk_running_job(job_service, unit_type="dir")

    # Pre-create a conflicting destination file in the stage tree.
    dst = tmp_path / "stage" / "import" / "stage" / job_id / "book" / "a.mp3"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(b"keep")

    state = ImportRunState(
        source_selection_snapshot={},
        source_handling_mode="stage",
        global_options={
            "conflict_policy": "skip",
        },
    )

    import_job.run_import_job(
        job_id=job_id,
        job_service=job_service,
        fs=fs,
        registry=registry,
        run_state=state,
        source_root=RootName.INBOX,
        book_rel_path="book",
    )

    assert dst.read_bytes() == b"keep"
