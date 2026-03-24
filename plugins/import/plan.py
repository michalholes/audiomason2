"""Plan computation for import wizard engine.

This is a minimal baseline planner.

ASCII-only.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from .phase1_metadata_flow import build_phase1_metadata_projection
from .phase1_source_intake import build_phase1_source_projection


def _normalize_rel_path(value: str) -> str:
    rel = value.replace("\\", "/").strip("/")
    return "/".join(part for part in rel.split("/") if part)


def _strip_source_prefix(*, rel_path: str, source_prefix: str) -> str:
    if not source_prefix:
        return rel_path
    if rel_path == source_prefix:
        return ""
    prefix = source_prefix + "/"
    if rel_path.startswith(prefix):
        return rel_path[len(prefix) :]
    return rel_path


class PlanSelectionError(ValueError):
    """Raised when a plan cannot be computed due to invalid selection."""


def _canonical_target_relative_path(*, authority_meta: dict[str, Any] | None) -> str:
    authority = dict(authority_meta) if isinstance(authority_meta, dict) else {}
    author_label = _normalize_rel_path(str(authority.get("author_label") or ""))
    book_label = _normalize_rel_path(str(authority.get("book_label") or ""))
    if not author_label or not book_label:
        raise PlanSelectionError("canonical target authority missing")
    return _normalize_rel_path(f"{author_label}/{book_label}")


_PHASE2_AUDIO_SUFFIXES = {".m4a", ".m4b", ".mp3", ".opus"}


def _audio_rel_paths_for_unit(
    discovery: list[dict[str, Any]],
    *,
    relative_path: str,
    source_relative_path: str,
) -> list[str]:
    source_prefix = _normalize_rel_path(relative_path)
    scoped_prefix = _normalize_rel_path(source_relative_path)
    matched: list[str] = []
    for item in discovery:
        if not isinstance(item, dict):
            continue
        if str(item.get("kind") or "") not in {"file", "bundle"}:
            continue
        rel_any = item.get("relative_path")
        if not isinstance(rel_any, str):
            continue
        rel = _strip_source_prefix(
            rel_path=_normalize_rel_path(rel_any),
            source_prefix=source_prefix,
        )
        if scoped_prefix:
            if not (rel == scoped_prefix or rel.startswith(scoped_prefix + "/")):
                continue
            rel = rel[len(scoped_prefix) :].lstrip("/")
        suffix = PurePosixPath(rel).suffix.lower()
        if suffix in _PHASE2_AUDIO_SUFFIXES:
            matched.append(rel)
    return sorted(path for path in matched if path)


def _rename_outputs_for_unit(
    discovery: list[dict[str, Any]],
    *,
    relative_path: str,
    source_relative_path: str,
) -> list[str]:
    audio_rel_paths = _audio_rel_paths_for_unit(
        discovery,
        relative_path=relative_path,
        source_relative_path=source_relative_path,
    )
    count = len(audio_rel_paths) or 1
    return [f"{index:02d}.mp3" for index in range(1, count + 1)]


def _authority_book_meta(
    *,
    root: str,
    relative_path: str,
    discovery: list[dict[str, Any]],
    inputs: dict[str, Any],
    selected_book_ids: list[str],
    session_authority: dict[str, Any] | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    authority_any = dict(session_authority) if isinstance(session_authority, dict) else {}
    authority_book_meta_any = authority_any.get("authority_book_meta")
    authority_book_meta = (
        dict(authority_book_meta_any) if isinstance(authority_book_meta_any, dict) else {}
    )
    source_book_meta: dict[str, dict[str, Any]] = {}
    if authority_book_meta:
        source_projection = build_phase1_source_projection(
            discovery=discovery,
            state={
                "source": {"root": root, "relative_path": relative_path},
                "selected_book_ids": list(selected_book_ids),
            },
        )
        source_meta_any = source_projection.get("book_meta")
        source_book_meta = dict(source_meta_any) if isinstance(source_meta_any, dict) else {}
        return authority_book_meta, source_book_meta

    phase1_state = {
        "source": {"root": root, "relative_path": relative_path},
        "answers": dict(inputs),
        "selected_book_ids": list(selected_book_ids),
    }
    source_projection = build_phase1_source_projection(discovery=discovery, state=phase1_state)
    source_meta_any = source_projection.get("book_meta")
    source_book_meta = dict(source_meta_any) if isinstance(source_meta_any, dict) else {}
    metadata_projection = build_phase1_metadata_projection(
        source_projection=source_projection,
        state=phase1_state,
    )
    authority_meta_any = metadata_projection.get("authority_by_book")
    authority_book_meta = dict(authority_meta_any) if isinstance(authority_meta_any, dict) else {}
    return authority_book_meta, source_book_meta


def _filter_discovery_for_books(
    discovery: list[dict[str, Any]],
    selected_units: list[dict[str, str]],
    *,
    source_relative_path: str,
) -> list[dict[str, Any]]:
    source_prefix = _normalize_rel_path(source_relative_path)
    prefixes = []
    for u in selected_units:
        p = str(u.get("source_relative_path") or "")
        if p == "":
            # Selecting the session root implies selecting everything in discovery.
            return list(discovery)
        if p and not p.endswith("/"):
            p = p + "/"
        prefixes.append(p)

    if not prefixes:
        return []

    filtered: list[dict[str, Any]] = []
    for it in discovery:
        rel_any = it.get("relative_path")
        if not isinstance(rel_any, str):
            continue
        rel = _strip_source_prefix(
            rel_path=_normalize_rel_path(rel_any),
            source_prefix=source_prefix,
        )
        if any(rel == p[:-1] or rel.startswith(p) for p in prefixes if p):
            filtered.append(it)
    return filtered


def compute_plan(
    *,
    session_id: str,
    root: str,
    relative_path: str,
    discovery: list[dict[str, Any]],
    inputs: dict[str, Any],
    selected_book_ids: list[str],
    session_authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    authority_book_meta, source_book_meta = _authority_book_meta(
        root=root,
        relative_path=relative_path,
        discovery=discovery,
        inputs=inputs,
        selected_book_ids=selected_book_ids,
        session_authority=session_authority,
    )

    selected_units: list[dict[str, Any]] = []
    for book_id in selected_book_ids:
        if not isinstance(book_id, str):
            continue
        source_meta = dict(source_book_meta.get(book_id) or {})
        authority_meta = dict(authority_book_meta.get(book_id) or {})
        source_rel = _normalize_rel_path(str(source_meta.get("source_relative_path") or ""))
        if not authority_meta:
            raise PlanSelectionError("invalid selected_book_ids")
        display_label = str(authority_meta.get("display_label") or "")
        if not display_label:
            author_label = str(authority_meta.get("author_label") or "")
            book_label = str(authority_meta.get("book_label") or "")
            display_label = (
                author_label if author_label == book_label else f"{author_label} / {book_label}"
            )
        selected_units.append(
            {
                "book_id": book_id,
                "label": display_label.encode("ascii", errors="replace").decode("ascii"),
                "display_label": display_label,
                "source_relative_path": source_rel,
                "proposed_target_relative_path": _canonical_target_relative_path(
                    authority_meta=authority_meta
                ),
                "rename_outputs": _rename_outputs_for_unit(
                    discovery,
                    relative_path=relative_path,
                    source_relative_path=source_rel,
                ),
            }
        )

    selected_units = sorted(
        selected_units,
        key=lambda item: (str(item["label"]), str(item["book_id"])),
    )

    selected_discovery = _filter_discovery_for_books(
        discovery,
        selected_units,
        source_relative_path=relative_path,
    )
    files = sum(1 for it in selected_discovery if it.get("kind") == "file")
    dirs = sum(1 for it in selected_discovery if it.get("kind") == "dir")
    bundles = sum(1 for it in selected_discovery if it.get("kind") == "bundle")

    selected = {
        "filename_policy": inputs.get("filename_policy"),
        "covers_policy": inputs.get("covers_policy"),
        "id3_policy": inputs.get("id3_policy"),
        "audio_processing": inputs.get("audio_processing"),
        "publish_policy": inputs.get("publish_policy"),
        "delete_source_policy": inputs.get("delete_source_policy"),
        "skip_processed_books": inputs.get("skip_processed_books"),
        "conflict_policy": inputs.get("conflict_policy"),
        "parallelism": inputs.get("parallelism"),
    }

    return {
        "version": 1,
        "session_id": session_id,
        "source": {"root": root, "relative_path": relative_path},
        "selected_books": selected_units,
        "summary": {
            "selected_books": len(selected_units),
            "discovered_items": len(discovery),
            "files": files,
            "dirs": dirs,
            "bundles": bundles,
        },
        "selected_policies": selected,
    }
