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
