from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

JobMode = Literal["patch", "repair", "finalize_live", "finalize_workspace", "rerun_latest"]
JobStatus = Literal["queued", "running", "success", "fail", "canceled", "unknown"]


@dataclass
class JobRecord:
    job_id: str
    created_utc: str
    mode: JobMode
    issue_id: str
    commit_message: str
    patch_path: str
    raw_command: str
    canonical_command: list[str]
    status: JobStatus = "queued"
    started_utc: str | None = None
    ended_utc: str | None = None
    return_code: int | None = None
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunEntry:
    issue_id: int
    log_rel_path: str
    result: Literal["success", "fail", "unknown"]
    result_line: str | None
    mtime_utc: str


@dataclass
class StatsWindow:
    days: int
    total: int
    success: int
    fail: int
    unknown: int


@dataclass
class AppStats:
    all_time: StatsWindow
    windows: list[StatsWindow] = field(default_factory=list)
