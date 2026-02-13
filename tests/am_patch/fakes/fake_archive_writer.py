from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FakeArchiveResult:
    patched_zip: Path | None
    success_zip: Path | None


class FakeArchiveWriter:
    """A minimal archive writer used by tests.

    The root runner currently writes placeholder zips directly. This fake exists
    to support future refactors without changing the unit-test patterns.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[Path, str | None, bool]] = []

    def create_archives(
        self, repo_root: Path, issue_id: str | None, *, include_success: bool
    ) -> FakeArchiveResult:
        self.calls.append((repo_root, issue_id, include_success))
        patched = repo_root / "patches" / f"patched_issue_{issue_id or 'unknown'}.zip"
        success = None
        if include_success:
            success = repo_root / "patches" / f"patched_success_issue_{issue_id or 'unknown'}.zip"
        return FakeArchiveResult(patched_zip=patched, success_zip=success)
