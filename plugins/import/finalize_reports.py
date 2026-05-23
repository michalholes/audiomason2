"""Finalize artifacts for successful import PHASE 2 jobs.

ASCII-only.
"""

from __future__ import annotations

import json
from typing import TypeGuard

from plugins.file_io.service import FileService, RootName

from .processed_registry import iter_import_book_records
from .storage import atomic_write_json, atomic_write_text, read_json

_SCHEMA_VERSION = 1


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _as_dict_list(value: object) -> list[dict[str, object]]:
    if not _is_object_list(value):
        return []
    return [dict(item) for item in value if _is_str_object_dict(item)]


def _session_dir(session_id: str) -> str:
    return f"import/sessions/{session_id}"


def _finalize_dir(session_id: str) -> str:
    return f"{_session_dir(session_id)}/finalize"


def _artifact_ref(rel_path: str) -> str:
    return f"wizards:{rel_path}"


def build_dry_run_summary(job_requests: dict[str, object]) -> dict[str, object]:
    mode = str(job_requests.get("mode") or "")
    records = iter_import_book_records(job_requests)
    books: list[dict[str, object]] = []
    for record in records:
        authority = _as_str_object_dict(record.get("authority"))
        book = _as_str_object_dict(authority.get("book"))
        meta = _as_str_object_dict(authority.get("metadata_tags"))
        values = _as_str_object_dict(meta.get("values"))
        capabilities = _as_dict_list(record.get("capabilities"))
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
                "authority": authority,
                "capabilities": capabilities,
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
            "capabilities": sum(len(_as_dict_list(book.get("capabilities"))) for book in books),
        },
    }


def _book_artifact_paths(*, session_id: str, book: dict[str, object]) -> dict[str, str]:
    source = _as_str_object_dict(book.get("source"))
    source_rel = str(source.get("relative_path") or "")
    dry_run_name = str(book.get("dry_run_name") or "dryrun.txt")
    base = f"{_finalize_dir(session_id)}/{source_rel}" if source_rel else _finalize_dir(session_id)
    return {
        "processing_log": f"{base}/processing.log",
        "dry_run_text": f"{base}/{dry_run_name}",
    }


def _dry_run_text(*, job_id: str, book: dict[str, object]) -> str:
    source = _as_str_object_dict(book.get("source"))
    target = _as_str_object_dict(book.get("target"))
    authority = _as_str_object_dict(book.get("authority"))
    meta = _as_str_object_dict(authority.get("metadata_tags"))
    values = _as_str_object_dict(meta.get("values"))
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


def _build_report(
    *, job_id: str, job_requests: dict[str, object], report_path: str
) -> dict[str, object]:
    summary = build_dry_run_summary(job_requests)
    session_id = str(job_requests.get("session_id") or "")
    summary_books = _as_dict_list(summary.get("books"))
    books: list[dict[str, object]] = []
    processing_logs: dict[str, str] = {}
    dry_run_texts: dict[str, str] = {}
    for book in summary_books:
        paths = _book_artifact_paths(session_id=session_id, book=book)
        refs = {key: _artifact_ref(value) for key, value in paths.items()}
        processing_logs[str(book["book_id"])] = refs["processing_log"]
        dry_run_texts[str(book["book_id"])] = refs["dry_run_text"]
        books.append({**book, "artifacts": refs})
    counts = _as_str_object_dict(summary.get("counts"))
    return {
        "schema_version": _SCHEMA_VERSION,
        "job_id": job_id,
        "job_type": str(job_requests.get("job_type") or ""),
        "mode": str(job_requests.get("mode") or ""),
        "session_id": session_id,
        "status": "succeeded",
        "counts": counts,
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


def _write_processing_log(*, fs: FileService, rel_path: str, entry: dict[str, object]) -> None:
    text = json.dumps(entry, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    atomic_write_text(fs, RootName.WIZARDS, rel_path, text)


def _update_session_state(
    *,
    fs: FileService,
    session_id: str,
    job_id: str,
    report_path: str,
    report: dict[str, object],
) -> None:
    state_path = f"{_session_dir(session_id)}/state.json"
    if not fs.exists(RootName.WIZARDS, state_path):
        return
    state_any = read_json(fs, RootName.WIZARDS, state_path)
    if not _is_str_object_dict(state_any):
        return
    computed = state_any.get("computed")
    computed_map = _as_str_object_dict(computed)
    computed_map["finalize"] = {
        "job_id": job_id,
        "report_path": _artifact_ref(report_path),
        "artifacts": _as_str_object_dict(report.get("artifacts")),
        "counts": _as_str_object_dict(report.get("counts")),
        "status": "succeeded",
    }
    state_any["computed"] = computed_map
    state_any["status"] = "succeeded"
    atomic_write_json(fs, RootName.WIZARDS, state_path, state_any)


def write_success_finalize_artifacts(
    *,
    fs: FileService,
    job_id: str,
    job_requests: dict[str, object],
) -> dict[str, object] | None:
    """Persist deterministic finalize artifacts for a succeeded job."""

    session_id = str(job_requests.get("session_id") or "")
    if not session_id:
        return None

    report_path = f"{_finalize_dir(session_id)}/report.json"
    report = _build_report(job_id=job_id, job_requests=job_requests, report_path=report_path)
    for book in _as_dict_list(report.get("books")):
        refs = _as_str_object_dict(book.get("artifacts"))
        log_path = str(refs.get("processing_log") or "").removeprefix("wizards:")
        dry_run_path = str(refs.get("dry_run_text") or "").removeprefix("wizards:")
        source = _as_str_object_dict(book.get("source"))
        target = _as_str_object_dict(book.get("target"))
        authority = _as_str_object_dict(book.get("authority"))
        _write_processing_log(
            fs=fs,
            rel_path=log_path,
            entry={
                "book_id": str(book.get("book_id") or ""),
                "job_id": job_id,
                "source": source,
                "authority": authority,
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
