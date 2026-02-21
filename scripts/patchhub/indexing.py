from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from .models import AppStats, RunEntry, StatsWindow

_ANSI_RX = re.compile(r"\x1b\[[0-9;]*m")


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
        text = log_path.read_text(encoding="utf-8", errors="replace")
        result, result_line = parse_run_result_from_log_text(text)
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
