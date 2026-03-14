"""Deterministic PHASE 0/1 source intake projection for import sessions.

ASCII-only.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .fingerprints import sha256_hex
from .phase1_cover_flow import build_phase1_cover_projection
from .phase1_metadata_flow import build_phase1_metadata_projection
from .phase1_policy_flow import build_phase1_policy_projection


def _answer_dict(state: dict[str, Any], key: str) -> dict[str, Any]:
    answers_any = state.get("answers")
    answers = dict(answers_any) if isinstance(answers_any, dict) else {}
    value = answers.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _build_runtime_projection(
    *,
    state: dict[str, Any],
    metadata_projection: dict[str, Any],
    cover_projection: dict[str, Any],
    policy_projection: dict[str, Any],
    phase2_inputs: dict[str, Any],
) -> dict[str, Any]:
    conflicts_any = state.get("conflicts")
    conflicts = dict(conflicts_any) if isinstance(conflicts_any, dict) else {}
    has_conflicts = bool(conflicts.get("present")) or bool(conflicts.get("items"))
    conflict_policy = dict(phase2_inputs.get("conflict_policy") or {})
    conflict_mode = str(conflict_policy.get("mode") or "ask")

    final_summary_confirm = {"confirm_start": False}
    final_summary_confirm.update(_answer_dict(state, "final_summary_confirm"))

    computed_any = state.get("computed")
    computed = dict(computed_any) if isinstance(computed_any, dict) else {}
    summary_any = computed.get("plan_summary")
    summary = dict(summary_any) if isinstance(summary_any, dict) else {}

    selected_paths_any = cover_projection.get("selected_source_relative_paths")
    selected_paths = (
        [item for item in selected_paths_any if isinstance(item, str)]
        if isinstance(selected_paths_any, list)
        else []
    )

    return {
        "plan_preview_batch": {
            "summary": deepcopy(summary),
            "selected_source_relative_paths": deepcopy(selected_paths),
            "has_conflicts": has_conflicts,
        },
        "effective_author_title": deepcopy(
            dict(metadata_projection.get("effective_author_title") or {})
        ),
        "filename_policy": deepcopy(dict(metadata_projection.get("filename_policy") or {})),
        "covers_policy": deepcopy(dict(phase2_inputs.get("covers_policy") or {})),
        "id3_policy": deepcopy(dict(phase2_inputs.get("id3_policy") or {})),
        "audio_processing": deepcopy(dict(phase2_inputs.get("audio_processing") or {})),
        "publish_policy": deepcopy(dict(phase2_inputs.get("publish_policy") or {})),
        "delete_source_policy": deepcopy(dict(phase2_inputs.get("delete_source_policy") or {})),
        "conflict_policy": deepcopy(conflict_policy),
        "parallelism": deepcopy(dict(policy_projection.get("parallelism") or {})),
        "final_summary_confirm": final_summary_confirm,
        "resolve_conflicts_batch": {
            "confirm": False,
            "has_conflicts": has_conflicts,
            "required": conflict_mode == "ask" and has_conflicts,
            "policy": conflict_mode,
        },
        "phase2_inputs": deepcopy(phase2_inputs),
        "metadata": deepcopy(metadata_projection),
        "cover": deepcopy(cover_projection),
        "policy": deepcopy(policy_projection),
    }


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


def _scope_tail(scope_path: str) -> str:
    parts = [part for part in scope_path.split("/") if part]
    return parts[-1] if parts else "(root)"


def _scope_parent_tail(scope_path: str) -> str:
    parts = [part for part in scope_path.split("/") if part]
    return parts[-2] if len(parts) >= 2 else _scope_tail(scope_path)


def _collect_scoped_entries(
    *,
    discovery: list[dict[str, Any]],
    state: dict[str, Any],
) -> tuple[str, list[str], list[str]]:
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
    return source_prefix, dirs, files


def _scoped_depth(*, rel_path: str, is_file: bool) -> int:
    parts = [part for part in rel_path.split("/") if part]
    if is_file and parts:
        return len(parts[:-1])
    return len(parts)


def _scope_kind(*, source_prefix: str, dirs: list[str], files: list[str]) -> str:
    if not source_prefix:
        return "root"
    depths = [_scoped_depth(rel_path=rel, is_file=False) for rel in dirs if rel]
    depths.extend(_scoped_depth(rel_path=rel, is_file=True) for rel in files if rel)
    max_depth = max(depths, default=0)
    if max_depth >= 2:
        return "container"
    if max_depth == 1:
        return "author"
    if len([part for part in source_prefix.split("/") if part]) >= 2:
        return "book"
    return "container"


def _pairs_for_multilevel_scope(
    *,
    dirs: list[str],
    files: list[str],
) -> set[tuple[str, str, str]]:
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
    return pairs


def _pairs_for_author_scope(
    *,
    source_prefix: str,
    dirs: list[str],
    files: list[str],
) -> set[tuple[str, str, str]]:
    author_key = _scope_tail(source_prefix)
    pairs: set[tuple[str, str, str]] = set()
    for rel in dirs:
        parts = [part for part in rel.split("/") if part]
        if parts:
            pairs.add((author_key, parts[0], parts[0]))
    if not pairs:
        for rel in files:
            parent_parts = [part for part in rel.split("/") if part][:-1]
            if parent_parts:
                pairs.add((author_key, parent_parts[0], parent_parts[0]))
    if not pairs:
        pairs.add((author_key, author_key, ""))
    return pairs


def _pairs_for_book_scope(source_prefix: str) -> set[tuple[str, str, str]]:
    author_key = _scope_parent_tail(source_prefix)
    book_key = _scope_tail(source_prefix)
    return {(author_key, book_key, "")}


def _discovery_pairs(
    *,
    discovery: list[dict[str, Any]],
    state: dict[str, Any],
) -> tuple[list[tuple[str, str, str]], str]:
    source_prefix, dirs, files = _collect_scoped_entries(discovery=discovery, state=state)
    scope_kind = _scope_kind(source_prefix=source_prefix, dirs=dirs, files=files)
    if scope_kind in {"root", "container"}:
        pairs = _pairs_for_multilevel_scope(dirs=dirs, files=files)
    elif scope_kind == "author":
        pairs = _pairs_for_author_scope(
            source_prefix=source_prefix,
            dirs=dirs,
            files=files,
        )
    else:
        pairs = _pairs_for_book_scope(source_prefix)
    return sorted(pairs), scope_kind


def _book_pairs(
    *,
    discovery: list[dict[str, Any]],
    state: dict[str, Any],
) -> tuple[
    dict[str, list[str]],
    dict[str, dict[str, str]],
    list[str],
    list[str],
    str,
]:
    pairs, scope_kind = _discovery_pairs(discovery=discovery, state=state)

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

    return author_to_books, book_meta, author_ids, book_ids, scope_kind


def build_phase1_source_projection(
    *,
    discovery: list[dict[str, Any]],
    state: dict[str, Any],
) -> dict[str, Any]:
    author_to_books, book_meta, author_ids, book_ids, scope_kind = _book_pairs(
        discovery=discovery,
        state=state,
    )

    allow_autofill = scope_kind in {"root", "author", "book"}

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
    metadata_projection = build_phase1_metadata_projection(
        source_projection=source_projection,
        state=state,
    )
    cover_projection = build_phase1_cover_projection(
        discovery=discovery,
        source_projection=source_projection,
        state=state,
    )
    policy_projection = build_phase1_policy_projection(
        state=state,
        source_projection=source_projection,
    )
    phase2_inputs = {
        "covers_policy": {
            "mode": str(cover_projection.get("mode") or "skip"),
            "url": str(cover_projection.get("url") or ""),
            "choice": dict(cover_projection.get("choice") or {}),
            "candidates": [
                dict(item)
                for item in cover_projection.get("candidates", [])
                if isinstance(item, dict)
            ],
            "sources": [
                {
                    "source_relative_path": str(item.get("source_relative_path") or ""),
                    "candidates": [
                        dict(candidate)
                        for candidate in item.get("candidates", [])
                        if isinstance(candidate, dict)
                    ],
                }
                for item in cover_projection.get("sources", [])
                if isinstance(item, dict)
            ],
            "selected_source_relative_paths": [
                str(item)
                for item in cover_projection.get("selected_source_relative_paths", [])
                if isinstance(item, str)
            ],
            "has_single_candidate": bool(cover_projection.get("has_single_candidate", False)),
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
    phase1_projection = {
        **source_projection,
        "metadata": metadata_projection,
        "cover": cover_projection,
        "policy": policy_projection,
        "effective_author_title": dict(metadata_projection.get("effective_author_title") or {}),
        "filename_policy": dict(metadata_projection.get("filename_policy") or {}),
        "parallelism": dict(policy_projection.get("parallelism") or {}),
        "normalized_author": str(metadata_projection.get("normalize_author") or ""),
        "normalized_book_title": str(metadata_projection.get("normalize_book_title") or ""),
        "clean_inbox": str(policy_projection.get("clean_inbox") or "ask"),
        "skip_processed_books": bool(policy_projection.get("skip_processed_books", True)),
        "root_audio_baseline": dict(policy_projection.get("root_audio_baseline") or {}),
        "two_pass_order": list(policy_projection.get("two_pass_order") or []),
        "phase2_inputs": phase2_inputs,
    }
    phase1_projection["runtime"] = _build_runtime_projection(
        state=state,
        metadata_projection=metadata_projection,
        cover_projection=cover_projection,
        policy_projection=policy_projection,
        phase2_inputs=phase2_inputs,
    )
    return phase1_projection


__all__ = ["build_phase1_projection", "phase1_session_authority_applies"]
