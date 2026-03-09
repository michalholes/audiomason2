"""Finalize artifacts for successful import PHASE 2 jobs.

ASCII-only.
"""

from __future__ import annotations

import json
from typing import Any

from plugins.file_io.service import FileService, RootName

from .processed_registry import iter_import_book_records
from .storage import atomic_write_json, atomic_write_text, read_json

_SCHEMA_VERSION = 1


def _session_dir(session_id: str) -> str:
    return f"import/sessions/{session_id}"


def _finalize_dir(session_id: str) -> str:
    return f"{_session_dir(session_id)}/finalize"


def _artifact_ref(rel_path: str) -> str:
    return f"wizards:{rel_path}"


def build_dry_run_summary(job_requests: dict[str, Any]) -> dict[str, Any]:
    session_id = str(job_requests.get("session_id") or "")
    mode = str(job_requests.get("mode") or "")
    records = iter_import_book_records(job_requests)
    books = [
        {
            "book_id": str(record["book_id"]),
            "source": {
                "root": str(record["source_root"]),
                "relative_path": str(record["source_relative_path"]),
            },
            "target": {
                "root": str(record["target_root"]),
                "relative_path": str(record["target_relative_path"]),
            },
            "capabilities": list(record.get("capabilities") or []),
        }
        for record in records
    ]
    return {
        "schema_version": _SCHEMA_VERSION,
        "session_id": session_id,
        "mode": mode,
        "books": books,
        "counts": {
            "books": len(books),
            "capabilities": sum(len(book["capabilities"]) for book in books),
        },
    }


def _processing_log_entries(*, job_id: str, job_requests: dict[str, Any]) -> list[dict[str, Any]]:
    records = iter_import_book_records(job_requests)
    return [
        {
            "book_id": str(record["book_id"]),
            "job_id": job_id,
            "source": {
                "root": str(record["source_root"]),
                "relative_path": str(record["source_relative_path"]),
            },
            "status": "succeeded",
            "target": {
                "root": str(record["target_root"]),
                "relative_path": str(record["target_relative_path"]),
            },
        }
        for record in records
    ]


def _build_report(
    *,
    job_id: str,
    job_requests: dict[str, Any],
    dry_run_path: str,
    processing_log_path: str,
) -> dict[str, Any]:
    summary = build_dry_run_summary(job_requests)
    return {
        "schema_version": _SCHEMA_VERSION,
        "job_id": job_id,
        "job_type": str(job_requests.get("job_type") or ""),
        "mode": str(job_requests.get("mode") or ""),
        "session_id": str(job_requests.get("session_id") or ""),
        "status": "succeeded",
        "counts": dict(summary.get("counts") or {}),
        "artifacts": {
            "dry_run_summary": _artifact_ref(dry_run_path),
            "processing_log": _artifact_ref(processing_log_path),
        },
        "idempotency_key": str(job_requests.get("idempotency_key") or ""),
        "config_fingerprint": str(job_requests.get("config_fingerprint") or ""),
        "plan_fingerprint": str(job_requests.get("plan_fingerprint") or ""),
    }


def _write_processing_log(
    *,
    fs: FileService,
    rel_path: str,
    entries: list[dict[str, Any]],
) -> None:
    text = "".join(
        json.dumps(entry, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
        for entry in entries
    )
    atomic_write_text(fs, RootName.WIZARDS, rel_path, text)


def _update_session_state(
    *,
    fs: FileService,
    session_id: str,
    job_id: str,
    report_path: str,
    dry_run_path: str,
    processing_log_path: str,
) -> None:
    state_path = f"{_session_dir(session_id)}/state.json"
    if not fs.exists(RootName.WIZARDS, state_path):
        return
    state_any = read_json(fs, RootName.WIZARDS, state_path)
    if not isinstance(state_any, dict):
        return
    computed = state_any.get("computed")
    if not isinstance(computed, dict):
        computed = {}
    computed["finalize"] = {
        "dry_run_summary_path": _artifact_ref(dry_run_path),
        "job_id": job_id,
        "processing_log_path": _artifact_ref(processing_log_path),
        "report_path": _artifact_ref(report_path),
        "status": "succeeded",
    }
    state_any["computed"] = computed
    state_any["status"] = "succeeded"
    atomic_write_json(fs, RootName.WIZARDS, state_path, state_any)


def write_success_finalize_artifacts(
    *,
    fs: FileService,
    job_id: str,
    job_requests: dict[str, Any],
) -> dict[str, Any] | None:
    """Persist deterministic finalize artifacts for a succeeded job."""

    session_id = str(job_requests.get("session_id") or "")
    if not session_id:
        return None

    finalize_dir = _finalize_dir(session_id)
    dry_run_path = f"{finalize_dir}/dry_run_summary.json"
    processing_log_path = f"{finalize_dir}/processing_log.jsonl"
    report_path = f"{finalize_dir}/report.json"

    summary = build_dry_run_summary(job_requests)
    entries = _processing_log_entries(job_id=job_id, job_requests=job_requests)
    report = _build_report(
        job_id=job_id,
        job_requests=job_requests,
        dry_run_path=dry_run_path,
        processing_log_path=processing_log_path,
    )

    atomic_write_json(fs, RootName.WIZARDS, dry_run_path, summary)
    _write_processing_log(fs=fs, rel_path=processing_log_path, entries=entries)
    atomic_write_json(fs, RootName.WIZARDS, report_path, report)
    _update_session_state(
        fs=fs,
        session_id=session_id,
        job_id=job_id,
        report_path=report_path,
        dry_run_path=dry_run_path,
        processing_log_path=processing_log_path,
    )
    return report
