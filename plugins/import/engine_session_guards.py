"""Session input validation helpers for import engine.

This module is intentionally small and engine-facing.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from plugins.file_io.service.types import RootName

from .errors import validation_error


def validate_root_name(root: str) -> str | dict[str, Any]:
    root_s = str(root or "").strip()
    if not root_s:
        return validation_error(message="Missing root", path="$.root", reason="missing_root")
    try:
        RootName(root_s)
    except Exception:
        return validation_error(
            message="Invalid root",
            path="$.root",
            reason="invalid_root",
            meta={"root": root_s},
        )
    return root_s


def validate_relative_path(relative_path: str) -> str | dict[str, Any]:
    rel_s = str(relative_path or "").strip().replace("\\", "/")
    if not rel_s or rel_s == ".":
        rel_s = ""
    if rel_s.startswith("/"):
        return validation_error(
            message="relative_path must be relative",
            path="$.relative_path",
            reason="absolute_path_forbidden",
            meta={"relative_path": rel_s},
        )

    while "//" in rel_s:
        rel_s = rel_s.replace("//", "/")

    segs = [seg for seg in rel_s.split("/") if seg and seg != "."]
    if any(seg == ".." for seg in segs):
        return validation_error(
            message="Invalid relative_path",
            path="$.relative_path",
            reason="traversal_forbidden",
            meta={"relative_path": rel_s},
        )

    return "/".join(segs)


def validate_root_and_path(root: str, relative_path: str) -> tuple[str, str] | dict[str, Any]:
    root_v = validate_root_name(root)
    if isinstance(root_v, dict):
        return root_v

    rel_v = validate_relative_path(relative_path)
    if isinstance(rel_v, dict):
        return rel_v

    return root_v, rel_v
