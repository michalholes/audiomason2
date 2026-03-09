from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from .job_store import SqliteWebJobsStore
from .models import EventRow, JobRecord, LegacyJobSnapshot, VirtualEntry, WebJobsDbConfig

__all__ = [
    "EventRow",
    "JobRecord",
    "LegacyJobSnapshot",
    "VirtualEntry",
    "WebJobsDatabase",
    "WebJobsDbConfig",
    "iter_legacy_job_dirs",
    "load_web_jobs_db_config",
    "read_legacy_job_snapshot",
]


def _resolve_under_patches(patches_root: Path, rel_or_abs: str) -> Path:
    raw = str(rel_or_abs or "").strip()
    if not raw:
        return patches_root / "artifacts" / "web_jobs.sqlite3"
    path = Path(raw)
    if path.is_absolute():
        return path
    return (patches_root / path).resolve()


def _tuple_of_strings(raw: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(raw, list | tuple):
        return default
    items = tuple(str(item).strip() for item in raw if str(item).strip())
    return items or default


def load_web_jobs_db_config(repo_root: Path, patches_root: Path) -> WebJobsDbConfig:
    cfg_path = repo_root / "scripts" / "patchhub" / "patchhub.toml"
    raw: dict[str, Any] = {}
    if cfg_path.is_file():
        raw = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    db_raw = raw.get("web_jobs_db", {})
    migration_raw = raw.get("web_jobs_migration", {})
    backup_raw = raw.get("web_jobs_backup", {})
    recovery_raw = raw.get("web_jobs_recovery", {})
    fallback_raw = raw.get("web_jobs_fallback", {})
    retention_raw = raw.get("web_jobs_retention", {})
    derived_raw = raw.get("web_jobs_derived", {})
    fallback_virtual_enabled = bool(
        fallback_raw.get(
            "virtual_artifacts_web_jobs_enabled",
            derived_raw.get("virtual_artifacts_web_jobs_enabled", True),
        )
    )
    derived_virtual_enabled = bool(
        derived_raw.get(
            "virtual_artifacts_web_jobs_enabled",
            fallback_raw.get("virtual_artifacts_web_jobs_enabled", True),
        )
    )
    return WebJobsDbConfig(
        db_path=_resolve_under_patches(
            patches_root,
            str(db_raw.get("path", "artifacts/web_jobs.sqlite3")),
        ),
        busy_timeout_ms=max(1, int(db_raw.get("busy_timeout_ms", 5000))),
        connect_timeout_s=max(0.1, float(db_raw.get("connect_timeout_s", 5.0))),
        startup_migration_enabled=bool(migration_raw.get("startup_migration_enabled", False)),
        startup_verify_enabled=bool(migration_raw.get("startup_verify_enabled", False)),
        cleanup_enabled=bool(migration_raw.get("cleanup_enabled", False)),
        backup_destination_template=str(
            backup_raw.get(
                "destination_template",
                "artifacts/web_jobs_backup_{timestamp}.sqlite3",
            )
        ),
        backup_retain_count=max(0, int(backup_raw.get("retain_count", 5))),
        backup_verify_after_write=bool(backup_raw.get("verify_after_write", True)),
        backup_restore_source_preference=_tuple_of_strings(
            backup_raw.get("restore_source_preference"),
            ("explicit", "latest_backup"),
        ),
        recovery_restore_source_preference=_tuple_of_strings(
            recovery_raw.get("restore_source_preference"),
            ("explicit", "latest_backup", "main_db"),
        ),
        fallback_virtual_artifacts_web_jobs_enabled=fallback_virtual_enabled,
        derived_virtual_artifacts_web_jobs_enabled=derived_virtual_enabled,
        compatibility_enabled=fallback_virtual_enabled,
        retention_defaults={
            "jobs_keep_days": int(retention_raw.get("jobs_keep_days", 30)),
            "logs_keep_days": int(retention_raw.get("logs_keep_days", 30)),
            "events_keep_days": int(retention_raw.get("events_keep_days", 30)),
        },
        retention_thresholds={
            "compact_after_jobs": int(retention_raw.get("compact_after_jobs", 10000)),
            "compact_after_log_lines": int(retention_raw.get("compact_after_log_lines", 100000)),
            "compact_after_event_lines": int(
                retention_raw.get("compact_after_event_lines", 100000)
            ),
        },
    )


class WebJobsDatabase:
    def __init__(self, cfg: WebJobsDbConfig) -> None:
        self.cfg = cfg
        self._store = SqliteWebJobsStore(cfg)

    def load_job_json(self, job_id: str) -> dict[str, Any] | None:
        return self._store.load_job_json(job_id)

    def load_job_record(self, job_id: str) -> JobRecord | None:
        return self._store.load_job_record(job_id)

    def list_job_jsons(self, *, limit: int = 200) -> list[dict[str, Any]]:
        return self._store.list_job_jsons(limit=limit)

    def jobs_signature(self) -> tuple[int, int]:
        return self._store.jobs_signature()

    def upsert_job(self, job: JobRecord, *, count_as_job_change: bool = True) -> None:
        self._store.upsert_job(job, count_as_job_change=count_as_job_change)

    def replace_job_history(
        self,
        job: JobRecord,
        *,
        log_lines: list[str],
        event_lines: list[str],
    ) -> None:
        self._store.replace_job_history(job, log_lines=log_lines, event_lines=event_lines)

    def update_applied_files(self, job_id: str, files: list[str], source: str) -> None:
        self._store.update_applied_files(job_id, files, source)

    def mark_orphaned(self, job_id: str) -> JobRecord | None:
        return self._store.mark_orphaned(job_id)

    def append_log_line(self, job_id: str, line: str) -> int:
        return self._store.append_log_line(job_id, line)

    def append_event_line(self, job_id: str, raw_line: str) -> int:
        return self._store.append_event_line(job_id, raw_line)

    def read_log_tail(self, job_id: str, *, lines: int = 200) -> str:
        return self._store.read_log_tail(job_id, lines=lines)

    def read_full_log(self, job_id: str) -> str:
        return self._store.read_full_log(job_id)

    def read_event_rows(
        self,
        job_id: str,
        *,
        after_seq: int = 0,
        limit: int = 2000,
    ) -> list[EventRow]:
        return self._store.read_event_rows(job_id, after_seq=after_seq, limit=limit)

    def read_event_tail(self, job_id: str, *, lines: int = 500) -> tuple[list[EventRow], int]:
        return self._store.read_event_tail(job_id, lines=lines)

    def last_event_seq(self, job_id: str) -> int:
        return self._store.last_event_seq(job_id)

    def legacy_job_json_text(self, job_id: str) -> str | None:
        return self._store.legacy_job_json_text(job_id)

    def legacy_event_filename(self, job_id: str) -> str:
        return self._store.legacy_event_filename(job_id)

    def legacy_event_text(self, job_id: str) -> str:
        return self._store.legacy_event_text(job_id)

    def list_job_ids(self, *, limit: int = 2000) -> list[str]:
        return self._store.list_job_ids(limit=limit)

    def export_legacy_tree(self, dest_root: Path) -> None:
        self._store.export_legacy_tree(dest_root)

    def create_backup(self, *, destination_template: str | None = None) -> Path:
        return self._store.create_backup(destination_template=destination_template)

    def restore_backup(self, source: Path) -> None:
        self._store.restore_backup(source)


def read_legacy_job_snapshot(job_dir: Path) -> LegacyJobSnapshot:
    job_json: dict[str, Any] | None = None
    job_json_path = job_dir / "job.json"
    if job_json_path.is_file():
        try:
            job_json = json.loads(job_json_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            job_json = None
        if not isinstance(job_json, dict):
            job_json = None
    log_lines: list[str] = []
    log_path = job_dir / "runner.log"
    if log_path.is_file():
        log_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    event_lines: list[str] = []
    for path in sorted(job_dir.glob("*.jsonl")):
        event_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        break
    return LegacyJobSnapshot(
        job_id=job_dir.name,
        job_json=job_json,
        log_lines=log_lines,
        event_lines=event_lines,
    )


def iter_legacy_job_dirs(jobs_root: Path) -> list[Path]:
    if not jobs_root.is_dir():
        return []
    items = [path for path in jobs_root.iterdir() if path.is_dir()]
    items.sort(key=lambda path: path.name)
    return items
