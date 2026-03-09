# ruff: noqa: E402
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from patchhub.asgi.asgi_app import create_app
from patchhub.asgi.async_app_core import AsyncAppCore
from patchhub.config import load_config
from patchhub.models import JobRecord


async def _noop_async(self) -> None:
    return None


def test_db_primary_log_tail_endpoint_reads_from_sqlite_without_runner_log_file(
    tmp_path: Path,
) -> None:
    try:
        from fastapi.testclient import TestClient
    except Exception as exc:  # pragma: no cover
        raise AssertionError(str(exc)) from exc

    cfg = load_config(
        Path(__file__).resolve().parents[1] / "scripts" / "patchhub" / "patchhub.toml"
    )
    with (
        patch.object(AsyncAppCore, "startup", _noop_async),
        patch.object(AsyncAppCore, "shutdown", _noop_async),
    ):
        app = create_app(repo_root=tmp_path, cfg=cfg)
        db = app.state.core.web_jobs_db
        db.upsert_job(
            JobRecord(
                job_id="job-514-log",
                created_utc="2026-03-09T10:00:00Z",
                mode="patch",
                issue_id="514",
                commit_summary="DB primary",
                patch_basename="issue_514.zip",
                raw_command="python3 scripts/am_patch.py 514",
                canonical_command=["python3", "scripts/am_patch.py", "514"],
                status="success",
            )
        )
        db.append_log_line("job-514-log", "alpha")
        db.append_log_line("job-514-log", "beta")
        with TestClient(app) as client:
            resp = client.get("/api/jobs/job-514-log/log_tail", params={"lines": 1})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "job_id": "job-514-log", "tail": "beta"}
