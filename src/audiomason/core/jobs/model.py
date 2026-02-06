from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class JobType(StrEnum):
    PROCESS = "process"
    WIZARD = "wizard"
    DAEMON = "daemon"


class JobState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


_ALLOWED_TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.PENDING: {JobState.RUNNING, JobState.CANCELLED},
    JobState.RUNNING: {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED},
    JobState.SUCCEEDED: set(),
    JobState.FAILED: set(),
    JobState.CANCELLED: set(),
}


@dataclass(slots=True)
class Job:
    job_id: str
    type: JobType
    state: JobState = JobState.PENDING
    progress: float = 0.0

    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None

    cancel_requested: bool = False
    error: str | None = None

    meta: dict[str, str] = field(default_factory=dict)

    def transition(self, new_state: JobState) -> None:
        allowed = _ALLOWED_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(
                f"illegal job state transition: {self.state.value} -> {new_state.value}"
            )
        self.state = new_state

    def set_progress(self, value: float) -> None:
        if value < 0.0 or value > 1.0:
            raise ValueError("progress must be within [0.0, 1.0]")
        self.progress = value

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "type": self.type.value,
            "state": self.state.value,
            "progress": self.progress,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "cancel_requested": self.cancel_requested,
            "error": self.error,
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        return cls(
            job_id=str(data["job_id"]),
            type=JobType(str(data["type"])),
            state=JobState(str(data.get("state", JobState.PENDING.value))),
            progress=float(data.get("progress", 0.0)),
            created_at=data.get("created_at"),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            cancel_requested=bool(data.get("cancel_requested", False)),
            error=data.get("error"),
            meta=dict(data.get("meta", {})),
        )
