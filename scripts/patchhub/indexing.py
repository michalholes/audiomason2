from __future__ import annotations

import contextlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from .models import AppStats, RunEntry, StatsWindow

_ANSI_RX = re.compile(r"\x1b\[[0-9;]*m")
# Deterministic in-process cache for historical runs indexing.
# Invalidation is signature-based: (count, max mtime_ns) across matching log files.
_RUNS_CACHE: dict[tuple[str, str], tuple[tuple[int, int], list[RunEntry]]] = {}


def _utc_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def strip_ansi(s: str) -> str:
    return _ANSI_RX.sub("", s)


def parse_run_result_from_log_text(
    text: str,
) -> tuple[Literal["success", "fail", "unknown"], str | None]:
    lines = [strip_ansi(line_text).strip() for line_text in text.splitlines() if line_text.strip()]
    result_line: str | None = None
    for line in reversed(lines[-200:]):
        if line.startswith("RESULT:"):
            result_line = line
            break
    if result_line == "RESULT: SUCCESS":
        return "success", result_line
    if result_line == "RESULT: FAIL":
        return "fail", result_line
    return "unknown", result_line


def _tail_path(log_path: Path, *, tail_suffix: str = ".tail.txt") -> Path:
    # Idempotent: avoid runaway ".tail.txt.tail.txt..." if caller passes a tail file.
    name = log_path.name
    if name.endswith(tail_suffix):
        return log_path
    return log_path.with_name(name + tail_suffix)


def _read_sanitized_tail_text(log_path: Path) -> str | None:
    tail_path = _tail_path(log_path)
    if not tail_path.exists() or not tail_path.is_file():
        return None
    return tail_path.read_text(encoding="utf-8", errors="replace")


def _write_sanitized_tail_text(log_path: Path, text: str) -> None:
    tail_path = _tail_path(log_path)
    tmp_path = tail_path.with_name(tail_path.name + ".tmp")
    tmp_path.write_text(text, encoding="utf-8", errors="replace")
    tmp_path.replace(tail_path)


def _build_sanitized_tail_from_log(log_path: Path) -> str:
    # Read only the tail of the log (bounded IO) and strip ANSI only for those lines.
    max_bytes = 256 * 1024
    data: bytes
    with log_path.open("rb") as f:
        try:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
        except Exception:
            f.seek(0)
        data = f.read()
    chunk = data.decode("utf-8", errors="replace")
    raw_lines = [ln for ln in chunk.splitlines() if ln.strip()]
    # Keep enough context for RESULT parsing while keeping compute bounded.
    tail_lines = raw_lines[-400:]
    sanitized = [strip_ansi(ln).rstrip() for ln in tail_lines]
    return "\n".join(sanitized) + "\n"


def _ensure_sanitized_tail_text(log_path: Path) -> str:
    existing = _read_sanitized_tail_text(log_path)
    if existing is not None:
        return existing
    text = _build_sanitized_tail_from_log(log_path)
    # Best-effort cache; indexing must still succeed.
    with contextlib.suppress(Exception):
        _write_sanitized_tail_text(log_path, text)
    return text


def parse_run_result_from_sanitized_text(
    text: str,
) -> tuple[Literal["success", "fail", "unknown"], str | None]:
    # Input is already ANSI-free.
    lines = [line_text.strip() for line_text in text.splitlines() if line_text.strip()]
    result_line: str | None = None
    for line in reversed(lines[-200:]):
        if line.startswith("RESULT:"):
            result_line = line
            break
    if result_line == "RESULT: SUCCESS":
        return "success", result_line
    if result_line == "RESULT: FAIL":
        return "fail", result_line
    return "unknown", result_line


def runs_signature(patches_root: Path, log_filename_regex: str) -> tuple[int, int]:
    rx = re.compile(log_filename_regex)
    logs_dir = patches_root / "logs"
    if not logs_dir.exists() or not logs_dir.is_dir():
        return (0, 0)

    count = 0
    max_mtime_ns = 0
    for log_path in logs_dir.iterdir():
        if not log_path.is_file():
            continue
        if log_path.name.endswith(".tail.txt"):
            continue
        if not rx.search(log_path.name):
            continue
        try:
            st = log_path.stat()
        except Exception:
            continue
        count += 1
        if st.st_mtime_ns > max_mtime_ns:
            max_mtime_ns = st.st_mtime_ns
    return (count, max_mtime_ns)


def iter_runs(patches_root: Path, log_filename_regex: str) -> list[RunEntry]:
    rx = re.compile(log_filename_regex)
    logs_dir = patches_root / "logs"
    if not logs_dir.exists():
        return []

    count = 0
    max_mtime_ns = 0
    matched_paths: list[Path] = []
    for log_path in logs_dir.iterdir():
        if not log_path.is_file():
            continue
        if log_path.name.endswith(".tail.txt"):
            # Cache artifact, not a primary log.
            continue
        if not rx.search(log_path.name):
            continue
        try:
            st = log_path.stat()
        except Exception:
            continue
        matched_paths.append(log_path)
        count += 1
        if st.st_mtime_ns > max_mtime_ns:
            max_mtime_ns = st.st_mtime_ns

    key = (str(patches_root), log_filename_regex)
    sig = (count, max_mtime_ns)
    cached = _RUNS_CACHE.get(key)
    if cached is not None:
        cached_sig, cached_runs = cached
        if cached_sig == sig:
            return list(cached_runs)

    runs: list[RunEntry] = []
    for log_path in sorted(matched_paths):
        m = rx.search(log_path.name)
        if not m:
            continue
        try:
            issue_id = int(m.group(1))
        except (ValueError, IndexError):
            continue
        tail = _ensure_sanitized_tail_text(log_path)
        result, result_line = parse_run_result_from_sanitized_text(tail)
        st = log_path.stat()
        runs.append(
            RunEntry(
                issue_id=issue_id,
                log_rel_path=str(Path("logs") / log_path.name),
                result=result,
                result_line=result_line,
                mtime_utc=_utc_iso(st.st_mtime),
            )
        )

    runs.sort(key=lambda r: (r.mtime_utc, r.issue_id), reverse=True)
    _RUNS_CACHE[key] = (sig, runs)
    return runs


def compute_stats(runs: list[RunEntry], windows_days: list[int]) -> AppStats:
    now = datetime.now(UTC)

    def window(days: int) -> StatsWindow:
        cutoff = now.timestamp() - days * 86400
        filtered = [r for r in runs if _parse_iso(r.mtime_utc) >= cutoff]
        return _count(filtered, days)

    all_time = _count(runs, 0)
    return AppStats(all_time=all_time, windows=[window(d) for d in windows_days])


def _parse_iso(s: str) -> float:
    # s is in Z form
    dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    return dt.timestamp()


def _count(runs: list[RunEntry], days: int) -> StatsWindow:
    succ = sum(1 for r in runs if r.result == "success")
    fail = sum(1 for r in runs if r.result == "fail")
    unk = sum(1 for r in runs if r.result == "unknown")
    return StatsWindow(days=days, total=len(runs), success=succ, fail=fail, unknown=unk)
