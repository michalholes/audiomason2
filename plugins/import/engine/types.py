"""Import engine types.

ASCII-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ..session_store.types import ImportRunState

QueueMode = Literal["paused", "running"]


@dataclass(frozen=True)
class BookDecision:
    """Resolved non-interactive decision for a single book."""

    book_rel_path: str
    author: str
    title: str
    handling_mode: str
    options: dict[str, Any] | None = None


@dataclass(frozen=True)
class ImportJobRequest:
    """Request to create import jobs for a run."""

    run_id: str
    source_root: str
    state: ImportRunState
    decisions: list[BookDecision]


@dataclass(frozen=True)
class ImportQueueState:
    """Persisted queue state for import processing."""

    mode: QueueMode = "running"
