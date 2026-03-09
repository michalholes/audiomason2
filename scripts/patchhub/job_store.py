from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat as statlib
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import EventRow, JobRecord, WebJobsDbConfig

_SCHEMA = """
CREATE TABLE IF NOT EXISTS web_jobs (
    job_id TEXT PRIMARY KEY,
    created_utc TEXT NOT NULL,
    created_unix_ms INTEGER NOT NULL,
    mode TEXT NOT NULL,
    issue_id_raw TEXT NOT NULL,
    issue_id_int INTEGER,
    commit_summary TEXT NOT NULL,
    patch_basename TEXT,
    raw_command TEXT NOT NULL,
    canonical_command_json TEXT NOT NULL,
    status TEXT NOT NULL,
    started_utc TEXT,
    ended_utc TEXT,
    return_code INTEGER,
    error TEXT,
    cancel_requested_utc TEXT,
    cancel_ack_utc TEXT,
    cancel_source TEXT,
    original_patch_path TEXT,
    effective_patch_path TEXT,
    effective_patch_kind TEXT,
    selected_patch_entries_json TEXT NOT NULL,
    selected_repo_paths_json TEXT NOT NULL,
    applied_files_json TEXT NOT NULL,
    applied_files_source TEXT NOT NULL,
    last_log_seq INTEGER NOT NULL DEFAULT 0,
    last_event_seq INTEGER NOT NULL DEFAULT 0,
    row_rev INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS web_job_log_lines (
    job_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    line TEXT NOT NULL,
    PRIMARY KEY (job_id, seq)
);
CREATE TABLE IF NOT EXISTS web_job_event_lines (
    job_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    raw_line TEXT NOT NULL,
    ipc_seq INTEGER,
    frame_type TEXT,
    frame_event TEXT,
    PRIMARY KEY (job_id, seq)
);
CREATE TABLE IF NOT EXISTS web_jobs_meta (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    jobs_rev INTEGER NOT NULL,
    logs_rev INTEGER NOT NULL,
    events_rev INTEGER NOT NULL,
    updated_unix_ms INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_web_jobs_created_desc
    ON web_jobs(created_unix_ms DESC, job_id DESC);
CREATE INDEX IF NOT EXISTS idx_web_jobs_status_created
    ON web_jobs(status, created_unix_ms DESC, job_id DESC);
CREATE INDEX IF NOT EXISTS idx_web_jobs_issue_status_created
    ON web_jobs(issue_id_int, status, created_unix_ms DESC, job_id DESC);
CREATE INDEX IF NOT EXISTS idx_web_job_log_lines_tail
    ON web_job_log_lines(job_id, seq DESC);
CREATE INDEX IF NOT EXISTS idx_web_job_event_lines_tail
    ON web_job_event_lines(job_id, seq DESC);
"""

_DB_CACHE: dict[str, Any] = {}
_LIST_CACHE: dict[str, tuple[tuple[int, int], int, list[dict[str, Any]]]] = {}


def _utc_now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def _utc_to_unix_ms(value: str | None) -> int:
    if not value:
        return 0
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return 0
    return int(dt.replace(tzinfo=UTC).timestamp() * 1000)


def _safe_issue_id_int(value: str) -> int | None:
    raw = str(value or "").strip()
    if not raw.isdigit():
        return None
    return int(raw)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    try:
        obj = json.loads(raw)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _scan_job_dirs_and_sig(jobs_root: Path) -> tuple[tuple[int, int], list[str]]:
    try:
        it = os.scandir(jobs_root)
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return (0, 0), []

    names: list[str] = []
    count = 0
    max_mtime_ns = 0
    with it:
        for ent in it:
            if not ent.is_dir():
                continue
            name = ent.name
            names.append(name)
            jp = Path(jobs_root) / name / "job.json"
            try:
                st = jp.stat()
            except Exception:
                continue
            if not statlib.S_ISREG(st.st_mode):
                continue
            count += 1
            if int(st.st_mtime_ns) > max_mtime_ns:
                max_mtime_ns = int(st.st_mtime_ns)
    names.sort(reverse=True)
    return (count, max_mtime_ns), names


def _load_job_record_from_path(jobs_root: Path, job_id: str) -> JobRecord | None:
    payload = _read_json_file(jobs_root / str(job_id) / "job.json")
    if payload is None:
        return None
    try:
        return JobRecord.from_json(payload)
    except Exception:
        return None


class SqliteWebJobsStore:
    def __init__(self, cfg: WebJobsDbConfig) -> None:
        self.cfg = cfg
        self.cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.cfg.db_path),
            timeout=float(self.cfg.connect_timeout_s),
            isolation_level=None,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute(f"PRAGMA busy_timeout={int(self.cfg.busy_timeout_ms)}")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.execute(
                """
                INSERT INTO web_jobs_meta(
                    singleton,
                    jobs_rev,
                    logs_rev,
                    events_rev,
                    updated_unix_ms
                ) VALUES(1, 0, 0, 0, ?)
                ON CONFLICT(singleton) DO NOTHING
                """,
                (_utc_now_ms(),),
            )

    def _touch_meta(
        self,
        conn: sqlite3.Connection,
        *,
        jobs_delta: int = 0,
        logs_delta: int = 0,
        events_delta: int = 0,
    ) -> None:
        conn.execute(
            """
            UPDATE web_jobs_meta
               SET jobs_rev = jobs_rev + ?,
                   logs_rev = logs_rev + ?,
                   events_rev = events_rev + ?,
                   updated_unix_ms = ?
             WHERE singleton = 1
            """,
            (jobs_delta, logs_delta, events_delta, _utc_now_ms()),
        )

    def _row_to_job_json(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "job_id": str(row["job_id"]),
            "created_utc": str(row["created_utc"]),
            "created_unix_ms": int(row["created_unix_ms"]),
            "mode": str(row["mode"]),
            "issue_id": str(row["issue_id_raw"]),
            "commit_summary": str(row["commit_summary"]),
            "patch_basename": row["patch_basename"],
            "raw_command": str(row["raw_command"]),
            "canonical_command": json.loads(str(row["canonical_command_json"])),
            "status": str(row["status"]),
            "started_utc": row["started_utc"],
            "ended_utc": row["ended_utc"],
            "return_code": row["return_code"],
            "error": row["error"],
            "cancel_requested_utc": row["cancel_requested_utc"],
            "cancel_ack_utc": row["cancel_ack_utc"],
            "cancel_source": row["cancel_source"],
            "original_patch_path": row["original_patch_path"],
            "effective_patch_path": row["effective_patch_path"],
            "effective_patch_kind": row["effective_patch_kind"],
            "selected_patch_entries": json.loads(str(row["selected_patch_entries_json"])),
            "selected_repo_paths": json.loads(str(row["selected_repo_paths_json"])),
            "applied_files": json.loads(str(row["applied_files_json"])),
            "applied_files_source": str(row["applied_files_source"]),
            "last_log_seq": int(row["last_log_seq"]),
            "last_event_seq": int(row["last_event_seq"]),
            "row_rev": int(row["row_rev"]),
        }

    def _current_row_rev(self, conn: sqlite3.Connection, job_id: str) -> int:
        row = conn.execute(
            "SELECT row_rev FROM web_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return int(row["row_rev"]) if row is not None else 0

    def _job_values(
        self,
        job: JobRecord,
        *,
        log_count: int | None = None,
        event_count: int | None = None,
        row_rev: int,
    ) -> tuple[Any, ...]:
        payload = job.to_json()
        return (
            job.job_id,
            str(payload.get("created_utc", "")),
            int(payload.get("created_unix_ms", 0) or _utc_to_unix_ms(job.created_utc)),
            str(job.mode),
            str(job.issue_id),
            _safe_issue_id_int(job.issue_id),
            str(job.commit_summary),
            job.patch_basename,
            str(job.raw_command),
            _json_dumps(list(job.canonical_command)),
            str(job.status),
            job.started_utc,
            job.ended_utc,
            job.return_code,
            job.error,
            job.cancel_requested_utc,
            job.cancel_ack_utc,
            job.cancel_source,
            job.original_patch_path,
            job.effective_patch_path,
            job.effective_patch_kind,
            _json_dumps(list(job.selected_patch_entries)),
            _json_dumps(list(job.selected_repo_paths)),
            _json_dumps(list(job.applied_files)),
            str(job.applied_files_source),
            int(log_count if log_count is not None else job.last_log_seq),
            int(event_count if event_count is not None else job.last_event_seq),
            row_rev,
        )

    def _upsert_job_row(
        self,
        conn: sqlite3.Connection,
        job: JobRecord,
        *,
        log_count: int | None = None,
        event_count: int | None = None,
        row_rev: int,
    ) -> None:
        conn.execute(
            """
            INSERT INTO web_jobs(
                job_id, created_utc, created_unix_ms, mode,
                issue_id_raw, issue_id_int, commit_summary, patch_basename,
                raw_command, canonical_command_json, status,
                started_utc, ended_utc, return_code, error,
                cancel_requested_utc, cancel_ack_utc, cancel_source,
                original_patch_path, effective_patch_path, effective_patch_kind,
                selected_patch_entries_json, selected_repo_paths_json,
                applied_files_json, applied_files_source,
                last_log_seq, last_event_seq, row_rev
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?
            )
            ON CONFLICT(job_id) DO UPDATE SET
                created_utc = excluded.created_utc,
                created_unix_ms = excluded.created_unix_ms,
                mode = excluded.mode,
                issue_id_raw = excluded.issue_id_raw,
                issue_id_int = excluded.issue_id_int,
                commit_summary = excluded.commit_summary,
                patch_basename = excluded.patch_basename,
                raw_command = excluded.raw_command,
                canonical_command_json = excluded.canonical_command_json,
                status = excluded.status,
                started_utc = excluded.started_utc,
                ended_utc = excluded.ended_utc,
                return_code = excluded.return_code,
                error = excluded.error,
                cancel_requested_utc = excluded.cancel_requested_utc,
                cancel_ack_utc = excluded.cancel_ack_utc,
                cancel_source = excluded.cancel_source,
                original_patch_path = excluded.original_patch_path,
                effective_patch_path = excluded.effective_patch_path,
                effective_patch_kind = excluded.effective_patch_kind,
                selected_patch_entries_json = excluded.selected_patch_entries_json,
                selected_repo_paths_json = excluded.selected_repo_paths_json,
                applied_files_json = excluded.applied_files_json,
                applied_files_source = excluded.applied_files_source,
                last_log_seq = excluded.last_log_seq,
                last_event_seq = excluded.last_event_seq,
                row_rev = excluded.row_rev
            """,
            self._job_values(
                job,
                log_count=log_count,
                event_count=event_count,
                row_rev=row_rev,
            ),
        )

    def load_job_json(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM web_jobs WHERE job_id = ?",
                (str(job_id),),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_job_json(row)

    def load_job_record(self, job_id: str) -> JobRecord | None:
        payload = self.load_job_json(job_id)
        if payload is None:
            return None
        return JobRecord.from_json(payload)

    def list_job_jsons(self, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM web_jobs ORDER BY created_unix_ms DESC, job_id DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [self._row_to_job_json(row) for row in rows]

    def jobs_signature(self) -> tuple[int, int]:
        with self._connect() as conn:
            meta = conn.execute("SELECT jobs_rev FROM web_jobs_meta WHERE singleton = 1").fetchone()
            count_row = conn.execute("SELECT COUNT(*) FROM web_jobs").fetchone()
        rev = int(meta["jobs_rev"]) if meta is not None else 0
        count = int(count_row[0]) if count_row is not None else 0
        return count, rev

    def upsert_job(self, job: JobRecord, *, count_as_job_change: bool = True) -> None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT row_rev, last_log_seq, last_event_seq FROM web_jobs WHERE job_id = ?",
                (str(job.job_id),),
            ).fetchone()
            row_rev = (int(row["row_rev"]) if row is not None else 0) + 1
            log_count = max(
                int(getattr(job, "last_log_seq", 0) or 0),
                int(row["last_log_seq"]) if row is not None else 0,
            )
            event_count = max(
                int(getattr(job, "last_event_seq", 0) or 0),
                int(row["last_event_seq"]) if row is not None else 0,
            )
            self._upsert_job_row(
                conn,
                job,
                log_count=log_count,
                event_count=event_count,
                row_rev=row_rev,
            )
            self._touch_meta(conn, jobs_delta=1 if count_as_job_change else 0)
            conn.commit()

    def replace_job_history(
        self,
        job: JobRecord,
        *,
        log_lines: list[str],
        event_lines: list[str],
    ) -> None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row_rev = self._current_row_rev(conn, job.job_id) + 1
            self._upsert_job_row(
                conn,
                job,
                log_count=len(log_lines),
                event_count=len(event_lines),
                row_rev=row_rev,
            )
            conn.execute("DELETE FROM web_job_log_lines WHERE job_id = ?", (str(job.job_id),))
            conn.execute("DELETE FROM web_job_event_lines WHERE job_id = ?", (str(job.job_id),))
            if log_lines:
                conn.executemany(
                    "INSERT INTO web_job_log_lines(job_id, seq, line) VALUES (?, ?, ?)",
                    [(str(job.job_id), idx + 1, str(line)) for idx, line in enumerate(log_lines)],
                )
            if event_lines:
                items = []
                for idx, raw_line in enumerate(event_lines, start=1):
                    text = str(raw_line).rstrip("\n")
                    parsed = _read_event_frame(text)
                    items.append(
                        (
                            str(job.job_id),
                            idx,
                            text,
                            _int_or_none(parsed.get("seq")) if parsed is not None else None,
                            _none_if_blank(parsed.get("type")) if parsed is not None else None,
                            _none_if_blank(parsed.get("event")) if parsed is not None else None,
                        )
                    )
                conn.executemany(
                    """
                    INSERT INTO web_job_event_lines(
                        job_id, seq, raw_line, ipc_seq, frame_type, frame_event
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    items,
                )
            self._touch_meta(
                conn,
                jobs_delta=1,
                logs_delta=len(log_lines),
                events_delta=len(event_lines),
            )
            conn.commit()

    def update_applied_files(self, job_id: str, files: list[str], source: str) -> None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row_rev = self._current_row_rev(conn, str(job_id)) + 1
            conn.execute(
                """
                UPDATE web_jobs
                   SET applied_files_json = ?,
                       applied_files_source = ?,
                       row_rev = ?
                 WHERE job_id = ?
                """,
                (_json_dumps(list(files)), str(source), row_rev, str(job_id)),
            )
            self._touch_meta(conn, jobs_delta=1)
            conn.commit()

    def mark_orphaned(self, job_id: str) -> JobRecord | None:
        job = self.load_job_record(job_id)
        if job is None:
            return None
        if job.status not in {"queued", "running"}:
            return job
        job.status = "fail"
        if not job.ended_utc:
            job.ended_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        job.error = "orphaned: not in memory queue"
        self.upsert_job(job)
        return job

    def append_log_line(self, job_id: str, line: str) -> int:
        text = str(line or "")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT last_log_seq, row_rev FROM web_jobs WHERE job_id = ?",
                (str(job_id),),
            ).fetchone()
            if row is None:
                conn.rollback()
                return 0
            seq = int(row["last_log_seq"]) + 1
            row_rev = int(row["row_rev"]) + 1
            conn.execute(
                "INSERT INTO web_job_log_lines(job_id, seq, line) VALUES (?, ?, ?)",
                (str(job_id), seq, text),
            )
            conn.execute(
                "UPDATE web_jobs SET last_log_seq = ?, row_rev = ? WHERE job_id = ?",
                (seq, row_rev, str(job_id)),
            )
            self._touch_meta(conn, logs_delta=1)
            conn.commit()
        return seq

    def append_event_line(self, job_id: str, raw_line: str) -> int:
        text = str(raw_line or "").rstrip("\n")
        parsed = _read_event_frame(text)
        ipc_seq = _int_or_none(parsed.get("seq")) if parsed is not None else None
        frame_type = _none_if_blank(parsed.get("type")) if parsed is not None else None
        frame_event = _none_if_blank(parsed.get("event")) if parsed is not None else None
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT last_event_seq, row_rev FROM web_jobs WHERE job_id = ?",
                (str(job_id),),
            ).fetchone()
            if row is None:
                conn.rollback()
                return 0
            seq = int(row["last_event_seq"]) + 1
            row_rev = int(row["row_rev"]) + 1
            conn.execute(
                """
                INSERT INTO web_job_event_lines(
                    job_id, seq, raw_line, ipc_seq, frame_type, frame_event
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(job_id), seq, text, ipc_seq, frame_type, frame_event),
            )
            conn.execute(
                "UPDATE web_jobs SET last_event_seq = ?, row_rev = ? WHERE job_id = ?",
                (seq, row_rev, str(job_id)),
            )
            self._touch_meta(conn, events_delta=1)
            conn.commit()
        return seq

    def read_log_tail(self, job_id: str, *, lines: int = 200) -> str:
        limit = max(1, min(int(lines), 5000))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT line FROM web_job_log_lines
                 WHERE job_id = ?
                 ORDER BY seq DESC
                 LIMIT ?
                """,
                (str(job_id), limit),
            ).fetchall()
        return "\n".join(str(row["line"]) for row in reversed(rows))

    def read_full_log(self, job_id: str) -> str:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT line FROM web_job_log_lines WHERE job_id = ? ORDER BY seq ASC",
                (str(job_id),),
            ).fetchall()
        return "\n".join(str(row["line"]) for row in rows)

    def read_event_rows(
        self,
        job_id: str,
        *,
        after_seq: int = 0,
        limit: int = 2000,
    ) -> list[EventRow]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT seq, raw_line, ipc_seq, frame_type, frame_event
                  FROM web_job_event_lines
                 WHERE job_id = ? AND seq > ?
                 ORDER BY seq ASC
                 LIMIT ?
                """,
                (str(job_id), int(after_seq), max(1, int(limit))),
            ).fetchall()
        return [_event_row_from_sql(row) for row in rows]

    def read_event_tail(self, job_id: str, *, lines: int = 500) -> tuple[list[EventRow], int]:
        limit = max(1, min(int(lines), 5000))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT seq, raw_line, ipc_seq, frame_type, frame_event
                  FROM web_job_event_lines
                 WHERE job_id = ?
                 ORDER BY seq DESC
                 LIMIT ?
                """,
                (str(job_id), limit),
            ).fetchall()
        items = [_event_row_from_sql(row) for row in reversed(rows)]
        return items, (items[-1].seq if items else 0)

    def last_event_seq(self, job_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT last_event_seq FROM web_jobs WHERE job_id = ?",
                (str(job_id),),
            ).fetchone()
        return int(row["last_event_seq"]) if row is not None else 0

    def legacy_job_json_text(self, job_id: str) -> str | None:
        payload = self.load_job_json(job_id)
        if payload is None:
            return None
        return json.dumps(payload, ensure_ascii=True, indent=2)

    def legacy_event_filename(self, job_id: str) -> str:
        payload = self.load_job_json(job_id) or {}
        mode = str(payload.get("mode", ""))
        issue_id = str(payload.get("issue_id", ""))
        if mode in {"finalize_live", "finalize_workspace"}:
            return "am_patch_finalize.jsonl"
        if issue_id.isdigit():
            return f"am_patch_issue_{issue_id}.jsonl"
        return "am_patch_finalize.jsonl"

    def legacy_event_text(self, job_id: str) -> str:
        rows = self.read_event_rows(job_id, after_seq=0, limit=1_000_000)
        return "\n".join(row.raw_line for row in rows)

    def list_job_ids(self, *, limit: int = 2000) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT job_id FROM web_jobs ORDER BY created_unix_ms DESC, job_id DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [str(row["job_id"]) for row in rows]

    def export_legacy_tree(self, dest_root: Path) -> None:
        for job_id in self.list_job_ids(limit=1_000_000):
            job_dir = dest_root / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            job_text = self.legacy_job_json_text(job_id)
            if job_text is not None:
                (job_dir / "job.json").write_text(job_text + "\n", encoding="utf-8")
            (job_dir / "runner.log").write_text(self.read_full_log(job_id), encoding="utf-8")
            (job_dir / self.legacy_event_filename(job_id)).write_text(
                self.legacy_event_text(job_id),
                encoding="utf-8",
            )

    def create_backup(self, *, destination_template: str | None = None) -> Path:
        template = str(destination_template or self.cfg.backup_destination_template)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup_root = self.cfg.db_path.parent.parent
        dst = (backup_root / template.format(timestamp=timestamp)).resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as src_conn:
            src_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            with sqlite3.connect(str(dst)) as dst_conn:
                src_conn.backup(dst_conn)
        if self.cfg.backup_verify_after_write:
            with sqlite3.connect(str(dst)) as verify_conn:
                verify_conn.execute("PRAGMA quick_check")
        self._prune_backups(dst.parent, template)
        return dst

    def _prune_backups(self, backup_dir: Path, template: str) -> None:
        keep = int(self.cfg.backup_retain_count)
        if keep <= 0:
            return
        stem = Path(template).name.split("{timestamp}")[0]
        candidates = [p for p in backup_dir.iterdir() if p.is_file() and p.name.startswith(stem)]
        candidates.sort(key=lambda p: p.stat().st_mtime_ns, reverse=True)
        for path in candidates[keep:]:
            path.unlink(missing_ok=True)

    def restore_backup(self, source: Path) -> None:
        tmp_fd, tmp_name = tempfile.mkstemp(
            prefix=self.cfg.db_path.name + ".restore.",
            dir=str(self.cfg.db_path.parent),
        )
        os.close(tmp_fd)
        Path(tmp_name).unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(str(self.cfg.db_path) + suffix).unlink(missing_ok=True)
        try:
            shutil.copy2(source, tmp_name)
            Path(tmp_name).replace(self.cfg.db_path)
        finally:
            Path(tmp_name).unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(str(self.cfg.db_path) + suffix).unlink(missing_ok=True)
        self._init_db()


def _none_if_blank(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _read_event_frame(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _event_row_from_sql(row: sqlite3.Row) -> EventRow:
    return EventRow(
        seq=int(row["seq"]),
        raw_line=str(row["raw_line"]),
        ipc_seq=_int_or_none(row["ipc_seq"]),
        frame_type=_none_if_blank(row["frame_type"]),
        frame_event=_none_if_blank(row["frame_event"]),
    )


def _coerce_db(source: Any) -> Any:
    if hasattr(source, "load_job_json") and hasattr(source, "jobs_signature"):
        return source
    path = Path(source)
    key = str(path.resolve())
    cached = _DB_CACHE.get(key)
    if cached is not None:
        return cached
    from .web_jobs_db import WebJobsDatabase, load_web_jobs_db_config

    patches_root = path.parent.parent if path.name == "web_jobs" else path.parent
    repo_root = patches_root.parent if patches_root.name == "patches" else Path.cwd()
    db = WebJobsDatabase(load_web_jobs_db_config(repo_root, patches_root))
    _DB_CACHE[key] = db
    return db


def load_job_json(source: Any, job_id: str) -> dict[str, Any] | None:
    if isinstance(source, Path):
        return _read_json_file(source / str(job_id) / "job.json")
    return _coerce_db(source).load_job_json(job_id)


def load_job_record(source: Any, job_id: str) -> JobRecord | None:
    if isinstance(source, Path):
        return _load_job_record_from_path(source, job_id)
    return _coerce_db(source).load_job_record(job_id)


def job_json_signature(source: Any) -> tuple[int, int]:
    if isinstance(source, Path):
        sig, _names = _scan_job_dirs_and_sig(source)
        return sig
    return _coerce_db(source).jobs_signature()


def list_job_jsons_and_signature(
    source: Any,
    *,
    limit: int = 200,
) -> tuple[tuple[int, int], list[dict[str, Any]]]:
    limit = max(1, min(int(limit), 2000))
    if isinstance(source, Path):
        key = str(source)
        sig, names = _scan_job_dirs_and_sig(source)
        cached = _LIST_CACHE.get(key)
        if cached is not None:
            cached_sig, cached_limit, cached_val = cached
            if cached_sig == sig and limit <= cached_limit:
                return sig, list(cached_val[:limit])
        out: list[dict[str, Any]] = []
        for name in names:
            obj = _read_json_file(source / name / "job.json")
            if obj is None:
                continue
            out.append(obj)
            if len(out) >= limit:
                break
        _LIST_CACHE[key] = (sig, limit, out)
        return sig, out
    db = _coerce_db(source)
    return db.jobs_signature(), db.list_job_jsons(limit=limit)


def list_job_jsons(source: Any, *, limit: int = 200) -> list[dict[str, Any]]:
    _sig, out = list_job_jsons_and_signature(source, limit=limit)
    return out
