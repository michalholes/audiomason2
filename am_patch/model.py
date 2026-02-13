from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


class Phase(str, Enum):
    PREFLIGHT = "preflight"
    WORKSPACE = "workspace"
    PATCH = "patch"
    GATES_WORKSPACE = "gates_workspace"
    PROMOTE = "promote"
    GATES_LIVE = "gates_live"
    ARCHIVE = "archive"
    COMMIT = "commit"
    PUSH = "push"
    CLEANUP = "cleanup"


@dataclass(frozen=True)
class CLIArgs:
    """Normalized CLI inputs.

    This is intentionally a small subset of the full scripts/am_patch runner CLI.
    """

    issue_id: str | None
    commit_message: str | None
    patch_input: str | None

    finalize_message: str | None
    finalize_workspace: bool | None

    config_path: str | None
    verbosity: str | None
    test_mode: bool | None
    update_workspace: bool | None
    unified_patch: bool | None


@dataclass(frozen=True)
class RunnerConfig:
    verbosity: str
    test_mode: bool


@dataclass(frozen=True)
class ExecutionPlan:
    mode: str
    repo_root: Path
    config_path: Path
    config_sources: tuple[str, ...]
    phases: tuple[Phase, ...]
    parameters: Mapping[str, object]


@dataclass(frozen=True)
class PhaseResult:
    phase: Phase
    ok: bool
    detail: str = ""


class RunnerError(RuntimeError):
    """Base error for the root runner."""


class PhaseFailed(RunnerError):
    def __init__(self, phase: Phase, message: str) -> None:
        super().__init__(message)
        self.phase = phase


@dataclass(frozen=True)
class RunResult:
    ok: bool
    exit_code: int
    phase_results: tuple[PhaseResult, ...]
    events: tuple[str, ...]
    log_path: Path | None = None
