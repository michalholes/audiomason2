"""Preflight result models.

ASCII-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TextNormalization:
    """Deterministic text normalization settings.

    Used for ID3 majority vote and rename preview.
    """

    strip: bool = True
    collapse_whitespace: bool = True
    casefold: bool = True


@dataclass(frozen=True)
class Id3MajorityConfig:
    """ID3 majority vote configuration.

    Majority is computed over non-empty normalized values.
    """

    normalization: TextNormalization = TextNormalization()


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


@dataclass(frozen=True)
class IndexItem:
    """Fast index entry for root-level items (PHASE 0, no deep reads)."""

    rel_path: str
    item_type: str  # author_dir, book_dir, audio_file, container_zip, container_rar, other_file
    size: int | None = None
    mtime: float | None = None


@dataclass(frozen=True)
class IndexBook:
    """Fast index representation of a book unit."""

    book_ref: str
    unit_type: str  # dir | file
    author: str
    book: str
    rel_path: str

    # Optional enrichment fields (populated by background deep scan).
    suggested_author: str | None = None
    suggested_title: str | None = None
    cover_candidates: list[str] | None = None
    rename_preview: dict[str, str] | None = None
    fingerprint: BookFingerprint | None = None
    meta: dict[str, Any] | None = None


@dataclass(frozen=True)
class DeepScanState:
    """Background deep enrichment state."""

    state: str  # idle | pending | running | done | failed
    signature: str | None = None
    last_scan_ts: float | None = None
    scanned_items: int = 0
    total_items: int = 0
    last_error: str | None = None


@dataclass(frozen=True)
class IndexResult:
    """Fast index output for the import wizard start screen."""

    source_root_rel_path: str
    signature: str
    changed: bool
    last_scan_ts: float | None
    deep_scan_state: DeepScanState

    root_items: list[IndexItem]
    authors: list[str]
    books: list[IndexBook]
