from __future__ import annotations

from pathlib import Path

import pytest

from audiomason.core.context import ProcessingContext
from audiomason.core.jobs.model import JobState
from audiomason.core.orchestration import Orchestrator
from audiomason.core.orchestration_models import ProcessRequest, WizardRequest


def _write_empty_pipeline(path: Path) -> None:
    path.write_text(
        """pipeline:
  name: empty
  description: empty pipeline for tests
  steps: []
""",
        encoding="utf-8",
    )


def test_orchestrator_start_process_succeeds(
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

    log, _ = orchestrator.read_log(job_id)
    assert "succeeded" in log


def test_orchestrator_start_wizard_fails_phase2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    orchestrator = Orchestrator()
    job_id = orchestrator.start_wizard(WizardRequest(wizard_id="w1", payload={}))

    job = orchestrator.get_job(job_id)
    assert job.state == JobState.FAILED
    assert job.error is not None
