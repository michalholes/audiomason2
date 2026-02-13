from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from .compat import import_legacy


@dataclass(frozen=True)
class ArchiveResult:
    patched_zip: Path | None
    success_zip: Path | None


def create_archives(repo_root: Path, issue_id: str | None, *, include_success: bool) -> ArchiveResult:
    """Create deterministic archives under repo_root/patches/.

    For the root runner, archives are mode-conditional and may be skipped by the
    orchestrator. This helper is intentionally simple.
    """

    iid = issue_id or "unknown"
    out_dir = repo_root / "patches"
    out_dir.mkdir(parents=True, exist_ok=True)

    patched = out_dir / f"patched_issue_{iid}.zip"
    with zipfile.ZipFile(patched, "w", compression=zipfile.ZIP_DEFLATED) as z:
        # Minimal archive: include no files by default. The authoritative runner
        # builds richer archives; root runner can be extended later without
        # breaking determinism.
        z.writestr("README.txt", "patched archive placeholder\n")

    success: Path | None = None
    if include_success:
        success = out_dir / f"patched_success_issue_{iid}.zip"
        with zipfile.ZipFile(success, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("README.txt", "success archive placeholder\n")

    return ArchiveResult(patched_zip=patched, success_zip=success)


# Legacy compatibility for scripts runner.
try:
    _legacy = import_legacy("archive")
    archive_patch = _legacy.archive_patch  # type: ignore[attr-defined]
    make_failure_zip = _legacy.make_failure_zip  # type: ignore[attr-defined]
except Exception:
    pass
