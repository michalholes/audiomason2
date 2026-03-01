from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypeAlias

from .models import AppStats, RunEntry, StatsWindow

_ANSI_RX = re.compile(r"\x1b\[[0-9;]*m")

RunResult: TypeAlias = Literal["success", "fail", "unknown", "canceled"]

_LOG_CACHE: dict[str, tuple[tuple[int, int], tuple[RunResult, str | None]]] = {}


def _stat_key(p: Path) -> tuple[int, int]:
    st = p.stat()
    m_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000)))
    return m_ns, int(st.st_size)


def _tail_scan_result(
    path: Path,
    *,
    max_bytes: int = 256 * 1024,
    block_size: int = 8192,
) -> tuple[RunResult, str | None]:
    if not path.exists() or not path.is_file():
        return "unknown", None

    max_bytes = max(1, int(max_bytes))
    block_size = max(256, int(block_size))

    data = b""
    with path.open("rb") as f:
        try:
            f.seek(0, os.SEEK_END)
            end = int(f.tell())
        except Exception:
            end = 0

        pos = end
        while pos > 0 and len(data) < max_bytes:
            read_len = min(block_size, pos)
            pos -= read_len
            try:
                f.seek(pos, os.SEEK_SET)
                chunk = f.read(read_len)
            except Exception:
                break
            data = chunk + data
            if b"RESULT:" in data:
                break

    text = data.decode("utf-8", errors="replace")
    return parse_run_result_from_log_text(text)


def _utc_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def strip_ansi(s: str) -> str:
    return _ANSI_RX.sub("", s)


def parse_run_result_from_log_text(
    text: str,
) -> tuple[RunResult, str | None]:
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
    if result_line == "RESULT: CANCELED":
        return "canceled", result_line
    return "unknown", result_line


def iter_runs(patches_root: Path, log_filename_regex: str) -> list[RunEntry]:
    rx = re.compile(log_filename_regex)
    logs_dir = patches_root / "logs"
    if not logs_dir.exists():
        return []

    runs: list[RunEntry] = []
    for log_path in sorted(logs_dir.iterdir()):
        if not log_path.is_file():
            continue
        m = rx.search(log_path.name)
        if not m:
            continue
        try:
            issue_id = int(m.group(1))
        except (ValueError, IndexError):
            continue
        st = log_path.stat()
        key = (
            int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))),
            int(st.st_size),
        )
        result: RunResult
        result_line: str | None

        cache = _LOG_CACHE.get(str(log_path))
        if cache is not None and cache[0] == key:
            result, result_line = cache[1]
        else:
            result, result_line = _tail_scan_result(log_path)
            _LOG_CACHE[str(log_path)] = (key, (result, result_line))
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
    return runs


def compute_runs_directory_token(patches_root: Path) -> str:
    logs_dir = patches_root / "logs"
    if not logs_dir.exists() or not logs_dir.is_dir():
        return "no-logs"

    items: list[tuple[str, int, int]] = []
    for p in logs_dir.iterdir():
        if not p.is_file():
            continue
        try:
            st = p.stat()
        except Exception:
            continue
        m_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000)))
        items.append((p.name, m_ns, int(st.st_size)))

    items.sort()
    payload = json.dumps(items, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


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
