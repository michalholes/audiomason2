"""Deterministic conflict scanning for import wizard sessions.

This scans for existing target paths before creating jobs.

ASCII-only.
"""

from __future__ import annotations

from typing import TypeGuard, cast

from plugins.file_io.service import FileService, RootName


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _as_dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[object], value) if _is_str_object_dict(item)]


def _conflict_sort_key(conflict: dict[str, object]) -> tuple[str, str]:
    return (
        str(conflict.get("target_relative_path") or ""),
        str(conflict.get("source_book_id") or ""),
    )


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
    plan: dict[str, object],
    mode: str,
) -> list[dict[str, object]]:
    """Return a canonical list of conflicts derived from plan.json.

    Conflict scan MUST operate on planned outputs, not raw discovery.
    """

    tgt_root = _target_root(str(mode))

    selected = _as_dict_list(plan.get("selected_books"))

    if not selected:
        src_any = plan.get("source")
        if _is_str_object_dict(src_any):
            rel_any = src_any.get("relative_path")
            if isinstance(rel_any, str):
                selected = [
                    {
                        "book_id": f"implicit:{_normalize_rel_path(rel_any)}",
                        "proposed_target_relative_path": rel_any,
                    }
                ]

    conflicts: list[dict[str, object]] = []
    for it in selected:
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
        key=_conflict_sort_key,
    )
