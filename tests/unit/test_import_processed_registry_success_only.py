"""Issue 220: processed registry is updated only on successful import job completion."""

from __future__ import annotations

import asyncio
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest

from audiomason.core.config import ConfigResolver
from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus
from audiomason.core.jobs.api import JobService
from audiomason.core.jobs.model import JobType

ImportPlugin = import_module("plugins.import.plugin").ImportPlugin
RootName = import_module("plugins.file_io.service").RootName
atomic_write_json = import_module("plugins.import.storage").atomic_write_json
read_json = import_module("plugins.import.storage").read_json
processed_required = import_module("plugins.import.processed_registry_required")


def _make_resolver(tmp_path: Path) -> ConfigResolver:
    roots = {
        "inbox": tmp_path / "inbox",
        "stage": tmp_path / "stage",
        "outbox": tmp_path / "outbox",
        "jobs": tmp_path / "jobs",
        "config": tmp_path / "config",
        "wizards": tmp_path / "wizards",
    }
    for p in roots.values():
        p.mkdir(parents=True, exist_ok=True)
    defaults = {
        "file_io": {
            "roots": {
                "inbox_dir": str(roots["inbox"]),
                "stage_dir": str(roots["stage"]),
                "outbox_dir": str(roots["outbox"]),
                "jobs_dir": str(roots["jobs"]),
                "config_dir": str(roots["config"]),
                "wizards_dir": str(roots["wizards"]),
            }
        },
        "output_dir": str(roots["outbox"]),
        "diagnostics": {"enabled": False},
    }
    return ConfigResolver(
        cli_args=defaults,
        defaults=defaults,
        user_config_path=tmp_path / "no_user_config.yaml",
        system_config_path=tmp_path / "no_system_config.yaml",
    )


def test_processed_registry_updates_on_succeeded_diag_event(tmp_path: Path) -> None:
    # Reset globals to keep tests isolated.
    processed_required._INSTALLED = False
    bus = get_event_bus()
    bus.clear()

    resolver = _make_resolver(tmp_path)
    _ = ImportPlugin(resolver=resolver)

    job_requests_path = "import/sessions/s1/job_requests.json"
    job_requests = {
        "job_type": "import.process",
        "job_version": 1,
        "session_id": "s1",
        "mode": "stage",
        "config_fingerprint": "cfg",
        "actions": [
            {
                "type": "import.book",
                "book_id": "b1",
                "source": {"root": "inbox", "relative_path": "src/book"},
                "target": {"root": "stage", "relative_path": "dst/book"},
                "authority": {
                    "metadata_tags": {
                        "field_map": {"title": "book_title"},
                        "values": {"title": "Canonical Book"},
                        "track_start": 7,
                    }
                },
            }
        ],
        "idempotency_key": "idem",
        "diagnostics_context": {},
    }

    fs = import_module("plugins.file_io.service").FileService.from_resolver(resolver)
    atomic_write_json(fs, RootName.WIZARDS, job_requests_path, job_requests)

    meta = {
        "source": "import",
        "job_requests_path": f"wizards:{job_requests_path}",
    }
    job = JobService().create_job(JobType.PROCESS, meta=meta)

    # Non-success must not update.
    bus.publish(
        "diag.job.end",
        build_envelope(
            event="diag.job.end",
            component="jobs",
            operation="run_job",
            data={
                "job_id": str(job.job_id),
                "job_type": "process",
                "status": "failed",
                "duration_ms": 1,
            },
        ),
    )

    assert not fs.exists(RootName.WIZARDS, "import/processed/processed_registry.json")

    # Success must update.
    bus.publish(
        "diag.job.end",
        build_envelope(
            event="diag.job.end",
            component="jobs",
            operation="run_job",
            data={
                "job_id": str(job.job_id),
                "job_type": "process",
                "status": "succeeded",
                "duration_ms": 1,
            },
        ),
    )

    reg = read_json(fs, RootName.WIZARDS, "import/processed/processed_registry.json")
    assert isinstance(reg, dict)
    books = reg.get("books")
    assert isinstance(books, dict)
    assert "b1" in books
    entry = books["b1"]
    assert entry["idempotency_key"] == "idem"
    assert entry["config_fingerprint"] == "cfg"
    assert entry["authority"]["metadata_tags"]["track_start"] == 7


def test_subscriber_skips_shared_helper_owned_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    processed_required._INSTALLED = False
    bus = get_event_bus()
    bus.clear()

    resolver = _make_resolver(tmp_path)
    _ = ImportPlugin(resolver=resolver)

    job_requests_path = "import/sessions/s2/job_requests.json"
    job_requests = {
        "job_type": "import.process",
        "job_version": 1,
        "session_id": "s2",
        "mode": "stage",
        "config_fingerprint": "cfg",
        "actions": [
            {
                "type": "import.book",
                "book_id": "b2",
                "source": {"root": "inbox", "relative_path": "src/book"},
                "target": {"root": "stage", "relative_path": "dst/book"},
                "authority": {
                    "metadata_tags": {
                        "field_map": {"title": "book_title"},
                        "values": {"title": "Canonical Book"},
                    }
                },
            }
        ],
        "idempotency_key": "idem",
        "diagnostics_context": {},
    }

    fs = import_module("plugins.file_io.service").FileService.from_resolver(resolver)
    atomic_write_json(fs, RootName.WIZARDS, job_requests_path, job_requests)
    atomic_write_json(
        fs,
        RootName.WIZARDS,
        "import/sessions/s2/state.json",
        {"session_id": "s2", "status": "in_progress", "computed": {}},
    )

    meta = {
        "source": "import",
        "job_requests_path": f"wizards:{job_requests_path}",
    }
    job = JobService().create_job(JobType.PROCESS, meta=meta)

    completion_mod = import_module("plugins.import.process_contract_completion")
    completion_mod.apply_successful_process_completion(
        fs=fs,
        job_id=str(job.job_id),
        job_requests=job_requests,
    )

    calls: list[str] = []

    def _unexpected_call(**kwargs: Any) -> dict[str, Any] | None:
        calls.append(str(kwargs.get("job_id") or ""))
        return None

    monkeypatch.setattr(processed_required, "apply_successful_process_completion", _unexpected_call)

    bus.publish(
        "diag.job.end",
        build_envelope(
            event="diag.job.end",
            component="jobs",
            operation="run_job",
            data={
                "job_id": str(job.job_id),
                "job_type": "process",
                "status": "succeeded",
                "duration_ms": 1,
            },
        ),
    )

    assert calls == []


def test_live_completion_and_success_event_stay_exact_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    processed_required._INSTALLED = False
    bus = get_event_bus()
    bus.clear()

    resolver = _make_resolver(tmp_path)
    plugin = ImportPlugin(resolver=resolver)
    fs = import_module("plugins.file_io.service").FileService.from_resolver(resolver)

    job_requests_path = "import/sessions/s3/job_requests.json"
    job_requests = {
        "job_type": "import.process",
        "job_version": 1,
        "session_id": "s3",
        "mode": "stage",
        "config_fingerprint": "cfg",
        "actions": [
            {
                "type": "import.book",
                "book_id": "b3",
                "source": {"root": "inbox", "relative_path": "src/book"},
                "target": {"root": "stage", "relative_path": "dst/book"},
                "authority": {
                    "metadata_tags": {
                        "field_map": {"title": "book_title"},
                        "values": {"title": "Canonical Book"},
                    }
                },
            }
        ],
        "idempotency_key": "idem",
        "diagnostics_context": {},
    }
    atomic_write_json(fs, RootName.WIZARDS, job_requests_path, job_requests)
    atomic_write_json(
        fs,
        RootName.WIZARDS,
        "import/sessions/s3/state.json",
        {"session_id": "s3", "status": "in_progress", "computed": {}},
    )

    meta = {
        "source": "import",
        "job_requests_path": f"wizards:{job_requests_path}",
    }
    job = JobService().create_job(JobType.PROCESS, meta=meta)

    completion_mod = import_module("plugins.import.process_contract_completion")
    real_apply = completion_mod.apply_successful_process_completion
    calls: list[str] = []

    def _count_apply(**kwargs: Any) -> dict[str, Any] | None:
        calls.append(str(kwargs.get("job_id") or ""))
        return real_apply(**kwargs)

    monkeypatch.setattr(completion_mod, "apply_successful_process_completion", _count_apply)
    monkeypatch.setattr(processed_required, "apply_successful_process_completion", _count_apply)

    async def _fake_phase2(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(completion_mod, "run_phase2_job_requests", _fake_phase2)

    asyncio.run(
        completion_mod.run_process_contract_completion(
            engine=plugin.get_engine(),
            job_id=str(job.job_id),
            job_meta=meta,
            plugin_loader=object(),
        )
    )

    bus.publish(
        "diag.job.end",
        build_envelope(
            event="diag.job.end",
            component="jobs",
            operation="run_job",
            data={
                "job_id": str(job.job_id),
                "job_type": "process",
                "status": "succeeded",
                "duration_ms": 1,
            },
        ),
    )

    assert calls == [str(job.job_id)]
