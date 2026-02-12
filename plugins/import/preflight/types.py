"""Preflight result models.

ASCII-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BookFingerprint:
    """Deterministic fingerprint (basic)."""

    algo: str
    value: str
    strength: str = "basic"


@dataclass(frozen=True)
class BookPreflight:
    """Preflight data for a single book folder."""

    # Stable identifier for this discovered unit, scoped to a source root.
    book_ref: str

    # Unit type: "dir" for a discovered book directory, "file" for a single file unit
    # (archive or audio) discovered in the source root.
    unit_type: str

    author: str
    book: str
    rel_path: str

    suggested_author: str | None = None
    suggested_title: str | None = None

    cover_candidates: list[str] | None = None
    rename_preview: dict[str, str] | None = None

    fingerprint: BookFingerprint | None = None

    # Placeholder for future enrichment.
    meta: dict[str, Any] | None = None


@dataclass(frozen=True)
class PreflightResult:
    """Deterministic preflight output for a source root."""

    source_root_rel_path: str
    authors: list[str]
    books: list[BookPreflight]

    # Any non-book entries explicitly skipped.
    skipped: list[SkippedEntry]


@dataclass(frozen=True)
class SkippedEntry:
    """Entry skipped during preflight with an explicit reason."""

    rel_path: str
    entry_type: str
    reason: str
