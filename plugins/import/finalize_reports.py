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
    mode = str(job_requests.get("mode") or "")
    records = iter_import_book_records(job_requests)
    books = []
    for record in records:
        book = dict(record.get("authority") or {}).get("book") or {}
        meta = dict(dict(record.get("authority") or {}).get("metadata_tags") or {})
        values = dict(meta.get("values") or {})
        author = str(
            values.get("artist") or values.get("album_artist") or book.get("author_label") or ""
        )
        title = str(values.get("title") or values.get("album") or book.get("book_label") or "")
        books.append(
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
                "authority": dict(record.get("authority") or {}),
                "capabilities": list(record.get("capabilities") or []),
                "dry_run_name": f"{author} - {title}.dryrun.txt",
            }
        )
    return {
        "schema_version": _SCHEMA_VERSION,
        "session_id": str(job_requests.get("session_id") or ""),
        "mode": mode,
        "books": books,
        "counts": {
            "books": len(books),
            "capabilities": sum(len(book["capabilities"]) for book in books),
        },
    }


def _book_artifact_paths(*, session_id: str, book: dict[str, Any]) -> dict[str, str]:
    source_rel = str(book.get("source", {}).get("relative_path") or "")
    dry_run_name = str(book.get("dry_run_name") or "dryrun.txt")
    base = f"{_finalize_dir(session_id)}/{source_rel}" if source_rel else _finalize_dir(session_id)
    return {
        "processing_log": f"{base}/processing.log",
        "dry_run_text": f"{base}/{dry_run_name}",
    }


def _dry_run_text(*, job_id: str, book: dict[str, Any]) -> str:
    source = dict(book.get("source") or {})
    target = dict(book.get("target") or {})
    authority = dict(book.get("authority") or {})
    meta = dict(authority.get("metadata_tags") or {})
    values = dict(meta.get("values") or {})
    lines = [
        f"job_id={job_id}",
        f"book_id={str(book.get('book_id') or '')}",
        f"source={str(source.get('root') or '')}:{str(source.get('relative_path') or '')}",
        f"target={str(target.get('root') or '')}:{str(target.get('relative_path') or '')}",
    ]
    for key in ("title", "artist", "album", "album_artist"):
        value = str(values.get(key) or "")
        if value:
            lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def _build_report(*, job_id: str, job_requests: dict[str, Any], report_path: str) -> dict[str, Any]:
    summary = build_dry_run_summary(job_requests)
    session_id = str(job_requests.get("session_id") or "")
    books = []
    processing_logs: dict[str, str] = {}
    dry_run_texts: dict[str, str] = {}
    for book in summary["books"]:
        paths = _book_artifact_paths(session_id=session_id, book=book)
        refs = {key: _artifact_ref(value) for key, value in paths.items()}
        processing_logs[str(book["book_id"])] = refs["processing_log"]
        dry_run_texts[str(book["book_id"])] = refs["dry_run_text"]
        books.append({**book, "artifacts": refs})
    return {
        "schema_version": _SCHEMA_VERSION,
        "job_id": job_id,
        "job_type": str(job_requests.get("job_type") or ""),
        "mode": str(job_requests.get("mode") or ""),
        "session_id": session_id,
        "status": "succeeded",
        "counts": dict(summary.get("counts") or {}),
        "artifacts": {
            "report": _artifact_ref(report_path),
            "processing_logs": processing_logs,
            "dry_run_texts": dry_run_texts,
        },
        "books": books,
        "idempotency_key": str(job_requests.get("idempotency_key") or ""),
        "config_fingerprint": str(job_requests.get("config_fingerprint") or ""),
        "plan_fingerprint": str(job_requests.get("plan_fingerprint") or ""),
    }


def _write_processing_log(*, fs: FileService, rel_path: str, entry: dict[str, Any]) -> None:
    text = json.dumps(entry, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    atomic_write_text(fs, RootName.WIZARDS, rel_path, text)


def _update_session_state(
    *,
    fs: FileService,
    session_id: str,
    job_id: str,
    report_path: str,
    report: dict[str, Any],
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
        "job_id": job_id,
        "report_path": _artifact_ref(report_path),
        "artifacts": dict(report.get("artifacts") or {}),
        "counts": dict(report.get("counts") or {}),
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

    report_path = f"{_finalize_dir(session_id)}/report.json"
    report = _build_report(job_id=job_id, job_requests=job_requests, report_path=report_path)
    for book in report["books"]:
        refs = dict(book.get("artifacts") or {})
        log_path = str(refs.get("processing_log") or "").removeprefix("wizards:")
        dry_run_path = str(refs.get("dry_run_text") or "").removeprefix("wizards:")
        source = dict(book.get("source") or {})
        target = dict(book.get("target") or {})
        _write_processing_log(
            fs=fs,
            rel_path=log_path,
            entry={
                "book_id": str(book.get("book_id") or ""),
                "job_id": job_id,
                "source": source,
                "authority": dict(book.get("authority") or {}),
                "status": "succeeded",
                "target": target,
            },
        )
        dry_run_text = _dry_run_text(job_id=job_id, book=book)
        atomic_write_text(fs, RootName.WIZARDS, dry_run_path, dry_run_text)
    atomic_write_json(fs, RootName.WIZARDS, report_path, report)
    _update_session_state(
        fs=fs,
        session_id=session_id,
        job_id=job_id,
        report_path=report_path,
        report=report,
    )
    return report
