"""Path normalization and root-jail resolution for file_io.

All paths are relative to a configured root directory.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from audiomason.core.diagnostics import build_envelope
from audiomason.core.errors import FileError
from audiomason.core.events import get_event_bus
from audiomason.core.logging import get_logger

from .types import RootName

_logger = get_logger(__name__)


def _short_traceback(*, max_lines: int = 20) -> str:
    tb_lines = traceback.format_exc().strip().splitlines()
    if len(tb_lines) <= max_lines:
        return "\n".join(tb_lines)
    return "\n".join(tb_lines[-max_lines:])


def _safe_publish(event: str, payload: dict[str, Any]) -> None:
    try:
        get_event_bus().publish(event, payload)
    except Exception:
        return


class PathOutsideRootError(FileError):
    """Raised when a requested path escapes the configured root."""


class InvalidRelativePathError(FileError):
    """Raised when a requested relative path is invalid."""


@dataclass(frozen=True)
class RootConfig:
    """Resolved root directory on disk."""

    name: RootName
    dir_path: Path


def normalize_rel_path(rel_path: str) -> PurePosixPath:
    """Normalize and validate a relative path.

    Rules:
    - must be relative (no leading slash)
    - no '..' segments
    - backslashes are treated as separators

    Returns:
        PurePosixPath for normalized relative path

    Raises:
        InvalidRelativePathError
    """
    if rel_path is None:
        raise InvalidRelativePathError("Path is required")

    # Normalize separators for consistent behavior across clients.
    rel_path = str(rel_path).replace("\\", "/")

    p = PurePosixPath(rel_path)

    if p.is_absolute():
        raise InvalidRelativePathError("Absolute paths are not allowed")

    parts = p.parts
    if any(part == ".." for part in parts):
        raise InvalidRelativePathError("Parent path segments ('..') are not allowed")

    # PurePosixPath('.') is valid and represents the root itself.
    return p


def resolve_path(root_dir: Path, rel_path: str, *, root_name: RootName | None = None) -> Path:
    """Resolve a relative path within a root directory.

    Raises:
        PathOutsideRootError
        InvalidRelativePathError
    """
    root_value = root_name.value if isinstance(root_name, RootName) else "unknown"
    start = time.perf_counter()

    base = {"root": root_value, "rel_path": rel_path}
    _safe_publish(
        "operation.start",
        build_envelope(
            event="operation.start",
            component="file_io",
            operation="file_io.resolve",
            data=dict(base),
        ),
    )

    try:
        rel = normalize_rel_path(rel_path)

        abs_path = (root_dir / Path(*rel.parts)).resolve()
        root_resolved = root_dir.resolve()

        # Ensure abs_path is inside root_dir.
        try:
            abs_path.relative_to(root_resolved)
        except ValueError:
            raise PathOutsideRootError("Path escapes configured root") from None

        duration_ms = int((time.perf_counter() - start) * 1000)
        end_data = {
            "root": root_value,
            "rel_path": rel_path,
            "resolved_path": str(abs_path),
            "status": "succeeded",
            "duration_ms": duration_ms,
        }
        _safe_publish(
            "operation.end",
            build_envelope(
                event="operation.end",
                component="file_io",
                operation="file_io.resolve",
                data=end_data,
            ),
        )
        _logger.info(
            f"file_io.resolve status=succeeded duration_ms={duration_ms} "
            f"root={root_value!r} rel_path={rel_path!r} resolved_path={str(abs_path)!r}"
        )
        return abs_path
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        end_data = {
            "root": root_value,
            "rel_path": rel_path,
            "status": "failed",
            "duration_ms": duration_ms,
            "error_type": type(e).__name__,
            "error_message": str(e),
            "traceback": _short_traceback(),
        }
        _safe_publish(
            "operation.end",
            build_envelope(
                event="operation.end",
                component="file_io",
                operation="file_io.resolve",
                data=end_data,
            ),
        )
        _logger.warning(
            f"file_io.resolve status=failed duration_ms={duration_ms} "
            f"root={root_value!r} rel_path={rel_path!r} error_type={type(e).__name__!r}"
        )
        raise
