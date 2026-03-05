from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

JobMode = Literal["patch", "repair", "finalize_live", "finalize_workspace", "rerun_latest"]
JobStatus = Literal["queued", "running", "success", "fail", "canceled", "unknown"]
RunResult = Literal["success", "fail", "unknown", "canceled"]


@dataclass
class JobRecord:
    job_id: str
    created_utc: str
    mode: JobMode
    issue_id: str
    commit_summary: str
    patch_basename: str | None
    raw_command: str
    canonical_command: list[str]
    status: JobStatus = "queued"
    started_utc: str | None = None
    ended_utc: str | None = None
    return_code: int | None = None
    error: str | None = None

    # Cancel metadata (Variant 2)
    cancel_requested_utc: str | None = None
    cancel_ack_utc: str | None = None
    cancel_source: str | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def compute_commit_summary(commit_message: str, *, max_len: int = 60) -> str:
    msg = str(commit_message or "")
    msg = " ".join(msg.split())
    if not msg:
        return ""
    if len(msg) <= max_len:
        return msg
    if max_len <= 3:
        return msg[:max_len]
    return msg[: max_len - 3] + "..."


def compute_patch_basename(patch_path: str) -> str | None:
    p = str(patch_path or "").strip()
    if not p:
        return None
    p = p.replace("\\", "/")
    if "/" in p:
        return p.rsplit("/", 1)[-1] or None
    return p


def job_to_list_item_json(j: JobRecord) -> dict[str, Any]:
    # Thin DTO for list endpoints (spec: JobListItem JSON).
    # Manual mapping to avoid dataclasses.asdict() overhead.
    return {
        "job_id": j.job_id,
        "status": j.status,
        "created_utc": j.created_utc,
        "started_utc": j.started_utc,
        "ended_utc": j.ended_utc,
        "mode": j.mode,
        "issue_id": j.issue_id,
        "commit_summary": j.commit_summary,
        "patch_basename": j.patch_basename,
    }


@dataclass
class RunEntry:
    issue_id: int
    log_rel_path: str
    result: RunResult
    result_line: str | None
    mtime_utc: str

    # Linked artifacts (may be empty when not found)
    archived_patch_rel_path: str | None = None
    diff_bundle_rel_path: str | None = None
    success_zip_rel_path: str | None = None


def run_to_list_item_json(r: RunEntry) -> dict[str, Any]:
    # Thin DTO for list endpoints (spec: RunListItem JSON).
    # artifact_refs is an array of rel paths (may be empty).
    refs: list[str] = []
    if r.archived_patch_rel_path:
        refs.append(str(r.archived_patch_rel_path))
    if r.diff_bundle_rel_path:
        refs.append(str(r.diff_bundle_rel_path))
    if r.success_zip_rel_path:
        refs.append(str(r.success_zip_rel_path))
    return {
        "issue_id": r.issue_id,
        "result": r.result,
        "mtime_utc": r.mtime_utc,
        "log_rel_path": r.log_rel_path,
        "artifact_refs": refs,
    }


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
