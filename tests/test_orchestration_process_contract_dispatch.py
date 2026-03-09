from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from audiomason.core.context import ProcessingContext
from audiomason.core.jobs.model import JobState, JobType
from audiomason.core.orchestration import Orchestrator
from audiomason.core.orchestration_models import ProcessRequest
from audiomason.core.process_job_contracts import IMPORT_PROCESS_CONTRACT_ID


class _FakeImportPlugin:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def run_process_contract(
        self, *, job_id: str, job_meta: dict[str, str], plugin_loader: Any
    ) -> None:
        self.calls.append(
            {
                "job_id": job_id,
                "job_meta": dict(job_meta),
                "plugin_loader": plugin_loader,
            }
        )


class _FakeLoader:
    def __init__(self, plugin: _FakeImportPlugin) -> None:
        self._plugin = plugin

    def get_plugin(self, name: str) -> Any:
        assert name == "import"
        return self._plugin


def _write_empty_pipeline(path: Path) -> None:
    path.write_text(
        """pipeline:\n  name: empty\n  description: empty pipeline for tests\n  steps: []\n""",
        encoding="utf-8",
    )


def test_run_job_dispatches_contract_process_to_plugin_entrypoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    orchestrator = Orchestrator()
    plugin = _FakeImportPlugin()
    loader = _FakeLoader(plugin)

    job = orchestrator.jobs.create_job(
        JobType.PROCESS,
        meta={
            "contract_id": IMPORT_PROCESS_CONTRACT_ID,
            "job_requests_path": "wizards:import/sessions/s1/job_requests.json",
        },
    )

    orchestrator.run_job(job.job_id, plugin_loader=loader)

    stored = orchestrator.get_job(job.job_id)
    assert stored.state == JobState.SUCCEEDED
    assert plugin.calls == [
        {
            "job_id": job.job_id,
            "job_meta": {
                "contract_id": IMPORT_PROCESS_CONTRACT_ID,
                "job_requests_path": "wizards:import/sessions/s1/job_requests.json",
                "verbosity_override": "1",
            },
            "plugin_loader": loader,
        }
    ]


def test_run_job_preserves_legacy_pipeline_dispatch_without_contract_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir(parents=True, exist_ok=True)
    pipeline_path = pipelines_dir / "empty.yaml"
    _write_empty_pipeline(pipeline_path)

    src = tmp_path / "input.mp3"
    src.write_bytes(b"dummy")

    ctx = ProcessingContext(id="ctx1", source=src)
    orchestrator = Orchestrator()

    req = ProcessRequest(contexts=[ctx], pipeline_path=pipeline_path, plugin_loader=None)
    job_id = orchestrator.start_process(req)

    job = orchestrator.get_job(job_id)
    assert job.state == JobState.SUCCEEDED
    assert job.progress == 1.0
