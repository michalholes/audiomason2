"""Deterministic conflict scanning for import wizard sessions.

This scans for existing target paths before creating jobs.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from plugins.file_io.service import FileService, RootName


def _normalize_rel_path(rel_path: str) -> str:
    p = str(rel_path).replace("\\", "/")
    if p.startswith("/"):
        p = p.lstrip("/")
    while "//" in p:
        p = p.replace("//", "/")
    if p == ".":
        p = ""
    segments = [seg for seg in p.split("/") if seg not in ("", ".")]
    if any(seg == ".." for seg in segments):
        raise ValueError("Invalid relative_path: '..' is forbidden")
    return "/".join(segments)


def _target_root(mode: str) -> RootName:
    if mode == "stage":
        return RootName.STAGE
    if mode == "inplace":
        return RootName.OUTBOX
    raise ValueError("mode must be 'stage' or 'inplace'")


def scan_conflicts(
    fs: FileService,
    *,
    root: str,
    relative_path: str,
    mode: str,
) -> list[dict[str, Any]]:
    """Return a canonical list of conflicts for the session.

    Current baseline: the target path mirrors the source relative_path under the
    chosen target root.
    """
    _ = root
    rel = _normalize_rel_path(relative_path)
    tgt_root = _target_root(str(mode))

    conflicts: list[dict[str, Any]] = []
    if rel and fs.exists(tgt_root, rel):
        conflicts.append({"root": tgt_root.value, "relative_path": rel})

    return sorted(conflicts, key=lambda x: (str(x.get("root")), str(x.get("relative_path"))))
