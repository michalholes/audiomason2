"""Unit tests for import.session_store run state persistence."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

ImportRunStateStore = importlib.import_module(
    "plugins.import.session_store.service"
).ImportRunStateStore
ImportRunState = importlib.import_module("plugins.import.session_store.types").ImportRunState
PreflightCacheMetadata = importlib.import_module(
    "plugins.import.session_store.types"
).PreflightCacheMetadata
ProcessedRegistryPolicy = importlib.import_module(
    "plugins.import.session_store.types"
).ProcessedRegistryPolicy


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


def test_import_run_state_round_trip(service: FileService) -> None:
    store = ImportRunStateStore(service)

    state = ImportRunState(
        source_selection_snapshot={"source_root": "inbox/books", "selected": ["A/B"]},
        source_handling_mode="stage",
        parallelism_n=1,
        global_options={"dry_run": True},
        conflict_policy={"mode": "placeholder"},
        filename_normalization_policy={"mode": "placeholder"},
        defaults_memory={"mode": "placeholder"},
        processed_registry_policy=ProcessedRegistryPolicy(enabled=True, scope="book_folder"),
        public_db_lookup={"mode": "placeholder"},
        preflight_cache=PreflightCacheMetadata(cache_key="k1", cache_hit=False),
    )

    run_id = "job_00000001"
    store.put(run_id, state)

    loaded = store.get(run_id)
    assert loaded == state

    store.delete(run_id)
    assert store.get(run_id) is None
