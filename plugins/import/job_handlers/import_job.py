"""Import job handler.

This is PHASE 2 processing. It must be non-interactive.

ASCII-only.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus
from audiomason.core.jobs.api import JobService
from audiomason.core.jobs.model import JobState
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

from ..processed_registry.service import ProcessedRegistry, fingerprint_key
from ..session_store.types import ImportRunState


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


_AUDIO_EXT = {".mp3", ".m4a", ".m4b", ".flac", ".wav", ".ogg", ".opus"}
_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def _emit_diag(event: str, *, operation: str, data: dict[str, Any]) -> None:
    try:
        env = build_envelope(
            event=event,
            component="import.engine.job_handler",
            operation=operation,
            data=data,
        )
        get_event_bus().publish(event, env)
    except Exception:
        return


def _ext(rel_path: str) -> str:
    name = rel_path.rstrip("/").split("/")[-1].lower()
    if "." not in name:
        return ""
    return "." + name.split(".")[-1]


def _fingerprint_identity_key(
    fs: FileService,
    *,
    source_root: RootName,
    book_rel_path: str,
    unit_type: str,
) -> str:
    """Compute the canonical processed identity key for a book unit.

    The algorithm matches Import Wizard preflight strong fingerprint.
    """
    if unit_type == "file":
        chk = fs.checksum(source_root, book_rel_path, algo="sha256")
        h = hashlib.sha256()
        h.update(book_rel_path.encode("utf-8"))
        h.update(b"\n")
        h.update(chk.encode("utf-8"))
        h.update(b"\n")
        return fingerprint_key(algo="sha256", value=h.hexdigest())

    entries = fs.list_dir(source_root, book_rel_path, recursive=True)
    files = [e.rel_path for e in entries if not e.is_dir]
    items: list[tuple[str, str]] = []
    for rel in sorted(files):
        ext = _ext(rel)
        if ext not in _AUDIO_EXT and ext not in _IMG_EXT:
            continue
        chk = fs.checksum(source_root, rel, algo="sha256")
        items.append((rel, chk))

    h = hashlib.sha256()
    for rel, chk in items:
        h.update(rel.encode("utf-8"))
        h.update(b"\n")
        h.update(chk.encode("utf-8"))
        h.update(b"\n")
    return fingerprint_key(algo="sha256", value=h.hexdigest())


def _copy_tree(
    fs: FileService,
    *,
    src_root: RootName,
    src_rel: str,
    dst_root: RootName,
    dst_rel: str,
) -> int:
    """Copy a directory tree deterministically.

    Returns number of copied files.
    """
    entries = fs.list_dir(src_root, src_rel, recursive=True)
    files = [e.rel_path for e in entries if not e.is_dir]
    copied = 0
    for rel in sorted(files):
        # Derive relative path within book folder.
        suffix = rel[len(src_rel.rstrip("/")) :].lstrip("/")
        dst_file_rel = f"{dst_rel.rstrip('/')}/{suffix}" if suffix else dst_rel

        with fs.open_read(src_root, rel) as r:
            data = r.read()
        with fs.open_write(dst_root, dst_file_rel, overwrite=True, mkdir_parents=True) as w:
            w.write(data)

        copied += 1
    return copied


def _copy_file(
    fs: FileService,
    *,
    src_root: RootName,
    src_rel: str,
    dst_root: RootName,
    dst_rel: str,
) -> int:
    """Copy a single file deterministically.

    Returns number of copied files (always 1).
    """
    with fs.open_read(src_root, src_rel) as r:
        data = r.read()
    with fs.open_write(dst_root, dst_rel, overwrite=True, mkdir_parents=True) as w:
        w.write(data)
    return 1


def _file_stem(name: str) -> str:
    base = name.rsplit("/", 1)[-1]
    if "." not in base:
        return base
    # Strip the last suffix only.
    return base.rsplit(".", 1)[0]


def run_import_job(
    *,
    job_id: str,
    job_service: JobService,
    fs: FileService,
    registry: ProcessedRegistry,
    run_state: ImportRunState,
    source_root: RootName,
    book_rel_path: str,
) -> None:
    """Execute a single import job."""
    _emit_diag(
        "boundary.start",
        operation="run_import_job",
        data={
            "job_id": job_id,
            "book_rel_path": book_rel_path,
            "mode": run_state.source_handling_mode,
        },
    )

    job = job_service.get_job(job_id)

    # unit_type is carried from preflight through the engine into job meta.
    unit_type_meta = job.meta.get("unit_type")
    unit_type = str(unit_type_meta) if unit_type_meta in ("dir", "file") else ""

    # Best-effort fallback: derive from filesystem if meta is missing.
    if not unit_type:
        try:
            st = fs.stat(source_root, book_rel_path)
            unit_type = "dir" if st.is_dir else "file"
        except Exception:
            unit_type = "dir"

    try:
        identity_key = _fingerprint_identity_key(
            fs,
            source_root=source_root,
            book_rel_path=book_rel_path,
            unit_type=unit_type,
        )

        if registry.is_processed(identity_key):
            job_service.append_log_line(
                job_id, f"already processed: {identity_key} rel={book_rel_path}"
            )
            job.set_progress(1.0)
            job.transition(JobState.SUCCEEDED)
            job.finished_at = _utcnow_iso()
            job_service.store.save_job(job)
            _emit_diag(
                "boundary.end",
                operation="run_import_job",
                data={"job_id": job_id, "status": "succeeded", "skipped": True},
            )
            return

        if run_state.source_handling_mode == "stage":
            fs.mkdir(RootName.STAGE, f"import/stage/{job_id}", parents=True, exist_ok=True)
            if unit_type == "dir":
                dst_base = f"import/stage/{job_id}/{book_rel_path}"
                copied = _copy_tree(
                    fs,
                    src_root=source_root,
                    src_rel=book_rel_path,
                    dst_root=RootName.STAGE,
                    dst_rel=dst_base,
                )
                job_service.append_log_line(
                    job_id, f"staged unit=dir files={copied} dst={dst_base}"
                )
            else:
                # Stage file units into a directory named after the file without extension.
                book_stem = _file_stem(book_rel_path)
                dst_folder = f"import/stage/{job_id}/{book_stem}"
                dst_file = book_rel_path.rsplit("/", 1)[-1]
                dst_rel = f"{dst_folder}/{dst_file}"
                copied = _copy_file(
                    fs,
                    src_root=source_root,
                    src_rel=book_rel_path,
                    dst_root=RootName.STAGE,
                    dst_rel=dst_rel,
                )
                job_service.append_log_line(
                    job_id, f"staged unit=file files={copied} dst={dst_rel}"
                )
        elif run_state.source_handling_mode == "inplace":
            job_service.append_log_line(job_id, f"inplace unit={unit_type} source={book_rel_path}")
        else:
            raise ValueError(f"Unsupported handling mode: {run_state.source_handling_mode}")

        # Optional destructive action: delete source after successful staging, guarded by
        # fingerprint identity to avoid TOCTOU behavior.
        delete_source = bool((run_state.global_options or {}).get("delete_source"))
        if run_state.source_handling_mode == "stage" and delete_source:
            try:
                current_key = _fingerprint_identity_key(
                    fs,
                    source_root=source_root,
                    book_rel_path=book_rel_path,
                    unit_type=unit_type,
                )
            except Exception as e:
                job_service.append_log_line(
                    job_id,
                    f"delete_source_fingerprint_failed: {type(e).__name__}: {e}",
                )
                current_key = None

            if current_key is None or current_key != identity_key:
                job_service.append_log_line(
                    job_id,
                    f"delete_source_guard_mismatch: expected={identity_key} got={current_key}",
                )
            else:
                try:
                    if unit_type == "dir":
                        fs.rmtree(source_root, book_rel_path)
                    else:
                        fs.delete_file(source_root, book_rel_path)
                    job_service.append_log_line(job_id, f"deleted_source: {book_rel_path}")
                except Exception as e:
                    job_service.append_log_line(
                        job_id,
                        f"delete_source_failed: {type(e).__name__}: {e}",
                    )
        job.set_progress(1.0)
        job.transition(JobState.SUCCEEDED)
        job.finished_at = _utcnow_iso()
        job_service.store.save_job(job)
        job_service.append_log_line(job_id, "succeeded")
        try:
            registry.mark_processed(identity_key)
        except Exception as e:
            job_service.append_log_line(
                job_id, f"processed_registry_mark_failed: {type(e).__name__}: {e}"
            )

        _emit_diag(
            "boundary.end",
            operation="run_import_job",
            data={"job_id": job_id, "status": "succeeded"},
        )
    except Exception as e:
        job.error = f"{type(e).__name__}: {e}"
        try:
            job.transition(JobState.FAILED)
        except Exception:
            job.state = JobState.FAILED
        job.finished_at = _utcnow_iso()
        job_service.store.save_job(job)
        job_service.append_log_line(job_id, f"failed: {job.error}")
        _emit_diag(
            "boundary.end",
            operation="run_import_job",
            data={"job_id": job_id, "status": "failed", "error": job.error},
        )
