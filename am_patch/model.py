from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping


class Phase(str, Enum):
    PREFLIGHT = "preflight"
    PATCH = "patch"
    GATES = "gates"
    PROMOTE = "promote"
    COMMIT = "commit"
    PUSH = "push"
    ARCHIVE = "archive"
    CLEANUP = "cleanup"


@dataclass(frozen=True)
class CLIArgs:
    """Normalized CLI inputs (planning-only).

    This is intentionally a small subset of the full scripts/am_patch runner CLI.
    The shadow runner accepts common flags and positional inputs needed to build
    a deterministic ExecutionPlan.
    """

    issue_id: str | None
    commit_message: str | None
    patch_input: str | None

    finalize_message: str | None
    finalize_workspace_issue_id: str | None

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
