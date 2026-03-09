# ruff: noqa: E402
from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from patchhub.web_jobs_migration import (
    _backup,
    _cleanup,
    _export_legacy,
    _migrate,
    _restore,
    _scan,
    _verify,
)


def _write_legacy_job(repo_root: Path, job_id: str = "job-514") -> Path:
    job_dir = repo_root / "patches" / "artifacts" / "web_jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "job_id": job_id,
        "created_utc": "2026-03-09T10:00:00Z",
        "mode": "patch",
        "issue_id": "514",
        "commit_summary": "DB primary",
        "patch_basename": "issue_514.zip",
        "raw_command": "python3 scripts/am_patch.py 514",
        "canonical_command": ["python3", "scripts/am_patch.py", "514"],
        "status": "success",
    }
    (job_dir / "job.json").write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (job_dir / "runner.log").write_text("alpha\nbeta\n", encoding="utf-8")
    (job_dir / "am_patch_issue_514.jsonl").write_text(
        '{"type":"log","msg":"queued"}\n{"type":"status","event":"done"}\n',
        encoding="utf-8",
    )
    return job_dir


def test_web_jobs_migration_is_idempotent_and_cleanup_is_explicit(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_legacy_job(repo_root)

    scan_items = _scan(repo_root)
    assert scan_items == [
        {
            "job_id": "job-514",
            "importable": True,
            "has_log": True,
            "has_events": True,
        }
    ]

    imported_first = _migrate(repo_root)
    imported_second = _migrate(repo_root)
    assert imported_first == ["job-514"]
    assert imported_second == ["job-514"]

    verify_items = _verify(repo_root)
    assert verify_items == [{"job_id": "job-514", "ok": True}]

    exported = Path(_export_legacy(repo_root))
    assert (exported / "job-514" / "job.json").is_file()
    assert (exported / "job-514" / "runner.log").read_text(encoding="utf-8") == "alpha\nbeta"
    assert (exported / "job-514" / "am_patch_issue_514.jsonl").read_text(encoding="utf-8") == (
        '{"type":"log","msg":"queued"}\n{"type":"status","event":"done"}'
    )

    removed = _cleanup(repo_root)
    assert removed == ["job-514"]
    assert not (repo_root / "patches" / "artifacts" / "web_jobs" / "job-514").exists()


def test_web_jobs_backup_and_restore_round_trip(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_legacy_job(repo_root, job_id="job-515")
    _migrate(repo_root)

    backup_path = Path(_backup(repo_root))
    assert backup_path.is_file()

    main_db = repo_root / "patches" / "artifacts" / "web_jobs.sqlite3"
    main_db.unlink()
    assert not main_db.exists()

    restored = Path(_restore(repo_root, backup_path))
    assert restored == backup_path
    assert main_db.is_file()
    assert _verify(repo_root) == [{"job_id": "job-515", "ok": True}]
