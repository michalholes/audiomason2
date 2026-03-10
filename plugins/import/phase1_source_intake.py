"""Deterministic PHASE 0/1 source intake projection for import sessions.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from .fingerprints import sha256_hex
from .phase1_cover_flow import build_phase1_cover_projection
from .phase1_metadata_flow import build_phase1_metadata_projection
from .phase1_policy_flow import build_phase1_policy_projection


def _selection_expr(*, ordered_ids: list[str], selected_ids: list[str]) -> str:
    if not ordered_ids:
        return ""
    if len(ordered_ids) == 1 and selected_ids == ordered_ids:
        return "1"
    if selected_ids == ordered_ids:
        return "all"
    index_map = {item_id: index for index, item_id in enumerate(ordered_ids, start=1)}
    indices = [index_map[item_id] for item_id in ordered_ids if item_id in set(selected_ids)]
    return ",".join(str(index) for index in indices)


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


def _discovery_pairs(
    *,
    discovery: list[dict[str, Any]],
    state: dict[str, Any],
) -> list[tuple[str, str, str]]:
    source_any = state.get("source")
    source = dict(source_any) if isinstance(source_any, dict) else {}
    source_prefix = _normalize_rel_path(str(source.get("relative_path") or ""))

    dirs: list[str] = []
    files: list[str] = []
    for item in discovery:
        if not isinstance(item, dict):
            continue
        rel_any = item.get("relative_path")
        if not isinstance(rel_any, str):
            continue
        rel = _strip_source_prefix(
            rel_path=_normalize_rel_path(rel_any),
            source_prefix=source_prefix,
        )
        kind = str(item.get("kind") or "")
        if kind == "dir":
            dirs.append(rel)
        elif kind in {"file", "bundle"}:
            files.append(rel)

    pairs: set[tuple[str, str, str]] = set()
    for rel in dirs:
        parts = [part for part in rel.split("/") if part]
        if len(parts) >= 2:
            pairs.add((parts[0], parts[1], f"{parts[0]}/{parts[1]}"))
    if not pairs:
        for rel in dirs:
            parts = [part for part in rel.split("/") if part]
            if parts:
                pairs.add((parts[0], parts[0], parts[0]))
    if not pairs:
        for rel in files:
            parts = [part for part in rel.split("/") if part]
            parent_parts = parts[:-1]
            if len(parent_parts) >= 2:
                pairs.add(
                    (
                        parent_parts[0],
                        parent_parts[1],
                        f"{parent_parts[0]}/{parent_parts[1]}",
                    )
                )
            elif len(parent_parts) == 1:
                pairs.add((parent_parts[0], parent_parts[0], parent_parts[0]))
            elif parts:
                pairs.add(("(root)", "(root)", ""))
    return sorted(pairs)


def _book_pairs(
    *,
    discovery: list[dict[str, Any]],
    state: dict[str, Any],
) -> tuple[dict[str, list[str]], dict[str, dict[str, str]], list[str], list[str], bool]:
    pairs = _discovery_pairs(discovery=discovery, state=state)

    authors: dict[str, dict[str, str]] = {}
    books: dict[str, dict[str, str]] = {}
    author_to_books: dict[str, list[str]] = {}
    book_meta: dict[str, dict[str, str]] = {}

    for author_key, book_key, source_relative_path in pairs:
        display_label = author_key if author_key == book_key else f"{author_key} / {book_key}"
        author_id = "author:" + sha256_hex(f"a|{author_key}".encode())[:16]
        book_id = "book:" + sha256_hex(f"b|{author_key}|{book_key}".encode())[:16]
        authors.setdefault(author_id, {"item_id": author_id, "label": author_key})
        books.setdefault(book_id, {"item_id": book_id, "label": display_label})
        author_to_books.setdefault(author_id, []).append(book_id)
        book_meta[book_id] = {
            "author_label": author_key,
            "book_label": book_key,
            "display_label": display_label,
            "source_relative_path": source_relative_path,
        }

    author_items = sorted(authors.values(), key=lambda item: (item["label"], item["item_id"]))
    book_items = sorted(books.values(), key=lambda item: (item["label"], item["item_id"]))
    author_ids = [item["item_id"] for item in author_items]
    book_ids = [item["item_id"] for item in book_items]

    for author_id in author_to_books:
        seen: set[str] = set()
        ordered: list[str] = []
        for book_id in book_ids:
            if book_id in author_to_books[author_id] and book_id not in seen:
                ordered.append(book_id)
                seen.add(book_id)
        author_to_books[author_id] = ordered

    source_any = state.get("source")
    source = dict(source_any) if isinstance(source_any, dict) else {}
    allow_autofill = str(source.get("relative_path") or "") == ""
    return author_to_books, book_meta, author_ids, book_ids, allow_autofill


def build_phase1_source_projection(
    *,
    discovery: list[dict[str, Any]],
    state: dict[str, Any],
) -> dict[str, Any]:
    author_to_books, book_meta, author_ids, book_ids, allow_autofill = _book_pairs(
        discovery=discovery,
        state=state,
    )

    selected_author_ids_any = state.get("selected_author_ids")
    selected_author_ids = (
        [
            item_id
            for item_id in selected_author_ids_any
            if isinstance(item_id, str) and item_id in set(author_ids)
        ]
        if isinstance(selected_author_ids_any, list)
        else []
    )
    if not selected_author_ids:
        selected_author_ids = list(author_ids) if len(author_ids) != 1 else [author_ids[0]]

    filtered_book_ids: list[str] = []
    for author_id in selected_author_ids:
        filtered_book_ids.extend(author_to_books.get(author_id, []))
    if not filtered_book_ids:
        filtered_book_ids = list(book_ids)
    filtered_book_ids = [book_id for book_id in book_ids if book_id in set(filtered_book_ids)]

    selected_book_ids_any = state.get("selected_book_ids")
    selected_book_ids = (
        [
            item_id
            for item_id in selected_book_ids_any
            if isinstance(item_id, str) and item_id in set(filtered_book_ids)
        ]
        if isinstance(selected_book_ids_any, list)
        else []
    )
    if not selected_book_ids:
        selected_book_ids = (
            list(filtered_book_ids) if len(filtered_book_ids) != 1 else [filtered_book_ids[0]]
        )

    return {
        "author_to_books": author_to_books,
        "book_meta": book_meta,
        "select_authors": {
            "ordered_ids": author_ids,
            "selection_expr": _selection_expr(
                ordered_ids=author_ids,
                selected_ids=selected_author_ids,
            ),
            "autofill_if": allow_autofill and len(author_ids) == 1,
            "selected_ids": selected_author_ids,
        },
        "select_books": {
            "ordered_ids": book_ids,
            "filtered_ids": filtered_book_ids,
            "selection_expr": _selection_expr(
                ordered_ids=book_ids,
                selected_ids=selected_book_ids,
            ),
            "autofill_if": allow_autofill and len(filtered_book_ids) == 1,
            "selected_ids": selected_book_ids,
            "selected_source_relative_paths": [
                book_meta.get(book_id, {}).get("source_relative_path", "")
                for book_id in selected_book_ids
                if isinstance(book_meta.get(book_id), dict)
            ],
        },
    }


def phase1_session_authority_applies(*, effective_model: dict[str, Any]) -> bool:
    steps_any = effective_model.get("steps")
    if not isinstance(steps_any, list):
        return False
    step_ids = {
        str(step.get("step_id") or "")
        for step in steps_any
        if isinstance(step, dict) and isinstance(step.get("step_id"), str)
    }
    return {"select_authors", "select_books"}.issubset(step_ids)


def build_phase1_projection(
    *,
    discovery: list[dict[str, Any]],
    state: dict[str, Any],
) -> dict[str, Any]:
    source_projection = build_phase1_source_projection(discovery=discovery, state=state)
    metadata_projection = build_phase1_metadata_projection(source_projection=source_projection)
    cover_projection = build_phase1_cover_projection(source_projection=source_projection)
    policy_projection = build_phase1_policy_projection(state=state)
    phase2_inputs = {
        "covers_policy": {
            "mode": str(cover_projection.get("mode") or "skip"),
            "url": str(cover_projection.get("url") or ""),
        },
        "id3_policy": {
            "field_map": dict(metadata_projection.get("field_map") or {}),
            "values": dict(metadata_projection.get("values") or {}),
        },
        "audio_processing": dict(policy_projection.get("audio_processing") or {}),
        "publish_policy": dict(policy_projection.get("publish_policy") or {}),
        "delete_source_policy": dict(policy_projection.get("delete_source_policy") or {}),
        "conflict_policy": dict(policy_projection.get("conflict_policy") or {}),
    }
    return {
        **source_projection,
        "metadata": metadata_projection,
        "cover": cover_projection,
        "policy": policy_projection,
        "normalized_author": str(metadata_projection.get("normalize_author") or ""),
        "normalized_book_title": str(metadata_projection.get("normalize_book_title") or ""),
        "clean_inbox": bool(policy_projection.get("clean_inbox", False)),
        "skip_processed_books": bool(policy_projection.get("skip_processed_books", True)),
        "root_audio_baseline": dict(policy_projection.get("root_audio_baseline") or {}),
        "two_pass_order": list(policy_projection.get("two_pass_order") or []),
        "phase2_inputs": phase2_inputs,
    }


__all__ = ["build_phase1_projection", "phase1_session_authority_applies"]
