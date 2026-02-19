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
    plan: dict[str, Any],
    mode: str,
) -> list[dict[str, Any]]:
    """Return a canonical list of conflicts derived from plan.json.

    Conflict scan MUST operate on planned outputs, not raw discovery.
    """

    tgt_root = _target_root(str(mode))

    selected_any = plan.get("selected_books")
    if not isinstance(selected_any, list):
        selected_any = []

    if not selected_any:
        src_any = plan.get("source")
        if isinstance(src_any, dict):
            rel_any = src_any.get("relative_path")
            if isinstance(rel_any, str):
                selected_any = [
                    {
                        "book_id": f"implicit:{_normalize_rel_path(rel_any)}",
                        "proposed_target_relative_path": rel_any,
                    }
                ]

    conflicts: list[dict[str, Any]] = []
    for it in selected_any:
        if not isinstance(it, dict):
            continue
        book_id_any = it.get("book_id")
        tgt_any = it.get("proposed_target_relative_path")
        if not isinstance(book_id_any, str) or not book_id_any:
            continue
        if not isinstance(tgt_any, str):
            continue

        rel = _normalize_rel_path(tgt_any)
        if not rel:
            # Root output is not a meaningful conflict target.
            continue

        if fs.exists(tgt_root, rel):
            conflicts.append(
                {
                    "target_relative_path": rel,
                    "reason": "exists",
                    "source_book_id": book_id_any,
                }
            )

    return sorted(
        conflicts,
        key=lambda x: (str(x.get("target_relative_path")), str(x.get("source_book_id"))),
    )
