"""Deterministic cover-policy projection for PHASE 1 import sessions.

ASCII-only.
"""

from __future__ import annotations

from typing import TypeGuard, cast

from plugins.file_io.service import FileService

from .cover_boundary import discover_cover_candidates
from .file_io_boundary import source_ref_from_state


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _answer_dict(state: dict[str, object], key: str) -> dict[str, object]:
    answers = _as_str_object_dict(state.get("answers"))
    value = answers.get(key)
    return _as_str_object_dict(value)


def _selected_paths(source_projection: dict[str, object]) -> list[str]:
    selected = _as_str_object_dict(source_projection.get("select_books"))
    selected_paths_any = selected.get("selected_source_relative_paths")
    return (
        [item for item in selected_paths_any if isinstance(item, str)]
        if _is_object_list(selected_paths_any)
        else []
    )


def _candidate_entries(
    *,
    source_relative_path: str,
    source_prefix: str,
    root_name: str,
    state: dict[str, object],
    fs: FileService | None,
) -> list[dict[str, str]]:
    source_root, _ = source_ref_from_state(state)
    if source_root is None or fs is None:
        return []
    return discover_cover_candidates(
        fs=fs,
        source_root=source_root,
        source_prefix=source_prefix,
        source_relative_path=source_relative_path,
        group_root=root_name,
    )


def _sanitize_candidates(result_any: object) -> list[dict[str, str]] | None:
    if not _is_object_list(result_any):
        return None
    out: list[dict[str, str]] = []
    for item in result_any:
        if _is_str_object_dict(item):
            out.append({str(key): str(value) for key, value in item.items()})
    return out


def _sanitize_candidates_by_source(result_any: object) -> dict[str, list[dict[str, str]]] | None:
    if not _is_str_object_dict(result_any):
        return None
    out: dict[str, list[dict[str, str]]] = {}
    for key, value in result_any.items():
        source_relative_path = str(key or "")
        if not source_relative_path:
            continue
        candidates = _sanitize_candidates(value)
        if candidates is None:
            continue
        out[source_relative_path] = candidates
    return out


def _sanitize_error_dict(error_any: object) -> dict[str, object] | None:
    if not _is_str_object_dict(error_any):
        return None
    out: dict[str, object] = {}
    for key, value in error_any.items():
        out[str(key)] = value
    return out


def _explicit_cover_entries_from_loop_results(result_any: object) -> list[dict[str, object]] | None:
    if not _is_object_list(result_any):
        return None
    entries: list[dict[str, object]] = []
    for item in result_any:
        if not _is_str_object_dict(item):
            continue
        subflow_any = item.get("subflow")
        subflow = dict(subflow_any) if _is_str_object_dict(subflow_any) else {}
        returns_any = subflow.get("returns")
        returns = dict(returns_any) if _is_str_object_dict(returns_any) else {}
        source_relative_path = str(
            returns.get("source_relative_path") or item.get("item") or ""
        ).strip()
        if not source_relative_path:
            continue
        candidates = _sanitize_candidates(returns.get("result")) or []
        entries.append(
            {
                "source_relative_path": source_relative_path,
                "candidates": candidates,
                "error": _sanitize_error_dict(returns.get("error")),
            }
        )
    return entries or None


def _explicit_cover_candidates_from_state(
    *,
    selected_paths: list[str],
    state: dict[str, object],
) -> list[dict[str, object]] | None:
    answer = _answer_dict(state, "cover_discover_initial")
    result_any = answer.get("result")
    error_any = answer.get("error")
    explicit_entries = _explicit_cover_entries_from_loop_results(result_any)
    if explicit_entries is not None:
        return [
            entry
            for entry in explicit_entries
            if str(entry.get("source_relative_path") or "") in selected_paths
        ]
    if answer and result_any is None and error_any is not None:
        source_relative_path = str(answer.get("source_relative_path") or "")
        if source_relative_path and source_relative_path in selected_paths:
            return [
                {
                    "source_relative_path": source_relative_path,
                    "candidates": [],
                    "error": _sanitize_error_dict(error_any),
                }
            ]
        if len(selected_paths) == 1:
            return [
                {
                    "source_relative_path": selected_paths[0],
                    "candidates": [],
                    "error": _sanitize_error_dict(error_any),
                }
            ]
        return []
    by_source = _sanitize_candidates_by_source(result_any)
    if by_source is not None:
        return [
            {
                "source_relative_path": source_relative_path,
                "candidates": list(candidates),
                "error": None,
            }
            for source_relative_path, candidates in by_source.items()
            if source_relative_path in selected_paths
        ]
    result = _sanitize_candidates(result_any)
    if result is None:
        return None
    if len(selected_paths) == 1:
        return [
            {
                "source_relative_path": selected_paths[0],
                "candidates": list(result),
                "error": None,
            }
        ]
    source_relative_path = str(answer.get("source_relative_path") or "")
    if source_relative_path and source_relative_path in selected_paths:
        return [
            {
                "source_relative_path": source_relative_path,
                "candidates": list(result),
                "error": None,
            }
        ]
    return []


def _build_cover_summary(
    *,
    per_source_candidates: list[dict[str, object]],
    error_any: object,
) -> str:
    top_level_error = dict(error_any) if _is_str_object_dict(error_any) else {}
    if top_level_error:
        message = str(
            top_level_error.get("message")
            or top_level_error.get("type")
            or "cover discovery failed"
        )
        return f"Cover autodetection failed: {message}"
    parts: list[str] = []
    for item in per_source_candidates:
        if not _is_str_object_dict(item):
            continue
        source_relative_path = str(item.get("source_relative_path") or "")
        item_error = _sanitize_error_dict(item.get("error"))
        if item_error:
            message = str(item_error.get("message") or item_error.get("type") or "failed")
            parts.append(f"{source_relative_path}: failed ({message})")
            continue
        candidates_any = item.get("candidates")
        candidates = (
            [dict(candidate) for candidate in candidates_any if _is_str_object_dict(candidate)]
            if _is_object_list(candidates_any)
            else []
        )
        if not candidates:
            parts.append(f"{source_relative_path}: none")
            continue
        kinds = ",".join(str(candidate.get("kind") or "") for candidate in candidates)
        parts.append(f"{source_relative_path}: {len(candidates)} [{kinds}]")
    if not parts:
        return "Cover autodetection: none"
    lines = [f"- {part}" for part in parts]
    return "Cover autodetection:\n" + "\n".join(lines)


def _allowed_modes_for_candidates(candidates: list[dict[str, str]]) -> list[str]:
    kinds = {str(candidate.get("kind") or "") for candidate in candidates}
    allowed = ["skip", "url"]
    if "embedded" in kinds:
        allowed.insert(0, "embedded")
    if "file" in kinds:
        insert_at = 1 if "embedded" in kinds else 0
        allowed.insert(insert_at, "file")
    return allowed


def _cover_loop_confirmed_by_source(state: dict[str, object]) -> dict[str, dict[str, str]]:
    vars_state = _as_str_object_dict(state.get("vars"))
    cover_loop = _as_str_object_dict(vars_state.get("cover_loop"))
    confirmed_any = cover_loop.get("confirmed")
    confirmed = _as_str_object_dict(confirmed_any)
    out: dict[str, dict[str, str]] = {}
    for source_relative_path, value in confirmed.items():
        source = str(source_relative_path or "").strip()
        if not source:
            continue
        choice = _as_str_object_dict(value)
        kind = str(choice.get("kind") or "").strip().lower()
        if kind not in {"skip", "url", "file", "embedded"}:
            kind = "skip"
        item: dict[str, str] = {"kind": kind}
        if kind == "url":
            item["url"] = str(choice.get("url") or "")
        out[source] = item
    return out


def _first_matching_candidate(
    *,
    candidates: list[dict[str, str]],
    requested_kind: str,
) -> dict[str, str] | None:
    for candidate in candidates:
        if str(candidate.get("kind") or "") == requested_kind:
            return dict(candidate)
    return None


def _resolve_choice_by_source(
    *,
    selected_paths: list[str],
    per_source_candidates: list[dict[str, object]],
    answer: dict[str, object],
    state: dict[str, object],
) -> tuple[dict[str, dict[str, str]], str, str, dict[str, str]]:
    candidates_by_source: dict[str, list[dict[str, str]]] = {}
    for item in per_source_candidates:
        if not _is_str_object_dict(item):
            continue
        source_relative_path = str(item.get("source_relative_path") or "")
        if not source_relative_path:
            continue
        candidates_by_source[source_relative_path] = (
            _sanitize_candidates(item.get("candidates")) or []
        )
    answer_choice_any = answer.get("choice")
    answer_choice = dict(answer_choice_any) if _is_str_object_dict(answer_choice_any) else {}
    requested_kind = str(answer_choice.get("kind") or answer.get("mode") or "").strip().lower()
    if not requested_kind and len(selected_paths) > 1:
        requested_kind = "per_book"
    requested_url = str(answer.get("url") or answer_choice.get("url") or "")
    requested_candidate_id = str(
        answer_choice.get("candidate_id") or answer.get("candidate_id") or ""
    )
    requested_source_relative_path = str(
        answer_choice.get("source_relative_path") or answer.get("source_relative_path") or ""
    )

    by_source: dict[str, dict[str, str]] = {}
    if requested_kind == "url" and requested_url:
        for source_relative_path in selected_paths:
            by_source[source_relative_path] = {"kind": "url", "url": requested_url}
        return by_source, "url", requested_url, {"kind": "url", "url": requested_url}

    if requested_kind == "candidate" and requested_candidate_id and requested_source_relative_path:
        matched = None
        for candidate in candidates_by_source.get(requested_source_relative_path, []):
            if str(candidate.get("candidate_id") or "") == requested_candidate_id:
                matched = dict(candidate)
                break
        for source_relative_path in selected_paths:
            if matched is not None and source_relative_path == requested_source_relative_path:
                by_source[source_relative_path] = {
                    "kind": "candidate",
                    "candidate_id": str(matched.get("candidate_id") or ""),
                    "source_relative_path": requested_source_relative_path,
                }
            else:
                by_source[source_relative_path] = {"kind": "skip"}
        choice = by_source.get(requested_source_relative_path, {"kind": "skip"})
        return by_source, str(choice.get("kind") or "skip"), "", choice

    if requested_kind == "per_book":
        overrides = _cover_loop_confirmed_by_source(state)
        for source_relative_path in selected_paths:
            requested = _as_str_object_dict(overrides.get(source_relative_path))
            mode = str(requested.get("kind") or "skip").strip().lower()
            if mode == "url":
                url = str(requested.get("url") or "")
                by_source[source_relative_path] = (
                    {"kind": "url", "url": url} if url else {"kind": "skip"}
                )
                continue
            if mode in {"file", "embedded"}:
                matched = _first_matching_candidate(
                    candidates=candidates_by_source.get(source_relative_path, []),
                    requested_kind=mode,
                )
                if matched is None:
                    by_source[source_relative_path] = {"kind": "skip"}
                else:
                    by_source[source_relative_path] = {
                        "kind": "candidate",
                        "candidate_id": str(matched.get("candidate_id") or ""),
                        "source_relative_path": source_relative_path,
                    }
                continue
            by_source[source_relative_path] = {"kind": "skip"}
        first_choice = (
            by_source.get(selected_paths[0], {"kind": "skip"})
            if selected_paths
            else {"kind": "skip"}
        )
        return by_source, "per_book", "", first_choice

    if requested_kind in {"file", "embedded"}:
        for source_relative_path in selected_paths:
            matched = _first_matching_candidate(
                candidates=candidates_by_source.get(source_relative_path, []),
                requested_kind=requested_kind,
            )
            if matched is None:
                by_source[source_relative_path] = {"kind": "skip"}
            else:
                by_source[source_relative_path] = {
                    "kind": "candidate",
                    "candidate_id": str(matched.get("candidate_id") or ""),
                    "source_relative_path": source_relative_path,
                }
    if selected_paths:
        first_choice = by_source.get(selected_paths[0], {"kind": "skip"})
    else:
        first_choice = {"kind": "skip"}
        return by_source, requested_kind, "", first_choice

    if len(selected_paths) == 1:
        only_path = selected_paths[0]
        first_candidate = next(iter(candidates_by_source.get(only_path, [])), None)
        if first_candidate is not None:
            choice = {
                "kind": "candidate",
                "candidate_id": str(first_candidate.get("candidate_id") or ""),
                "source_relative_path": only_path,
            }
            by_source[only_path] = choice
            return by_source, str(first_candidate.get("kind") or "skip"), "", choice

    for source_relative_path in selected_paths:
        by_source[source_relative_path] = {"kind": "skip"}
    return by_source, "skip", "", {"kind": "skip"}


def build_phase1_cover_projection(
    *,
    discovery: list[dict[str, object]],
    source_projection: dict[str, object],
    state: dict[str, object],
    fs: FileService | None = None,
) -> dict[str, object]:
    del discovery
    selected_paths = _selected_paths(source_projection)
    source = _as_str_object_dict(state.get("source"))
    source_prefix = str(source.get("relative_path") or "").replace("\\", "/").strip("/")
    root_name = str(source.get("root") or "")
    explicit_candidates = _explicit_cover_candidates_from_state(
        selected_paths=selected_paths,
        state=state,
    )
    if explicit_candidates is None:
        per_source_candidates: list[dict[str, object]] = [
            {
                "source_relative_path": source_relative_path,
                "candidates": _candidate_entries(
                    source_relative_path=source_relative_path,
                    source_prefix=source_prefix,
                    root_name=root_name,
                    state=state,
                    fs=fs,
                ),
            }
            for source_relative_path in selected_paths
        ]
    else:
        explicit_by_source = {
            str(item.get("source_relative_path") or ""): dict(item)
            for item in explicit_candidates
            if _is_str_object_dict(item)
        }
        per_source_candidates = []
        for source_relative_path in selected_paths:
            explicit = explicit_by_source.get(source_relative_path)
            if explicit is None:
                per_source_candidates.append(
                    {
                        "source_relative_path": source_relative_path,
                        "candidates": _candidate_entries(
                            source_relative_path=source_relative_path,
                            source_prefix=source_prefix,
                            root_name=root_name,
                            state=state,
                            fs=fs,
                        ),
                        "error": None,
                    }
                )
                continue
            per_source_candidates.append(
                {
                    "source_relative_path": source_relative_path,
                    "candidates": _sanitize_candidates(explicit.get("candidates")) or [],
                    "error": _sanitize_error_dict(explicit.get("error")),
                }
            )

    candidates: list[dict[str, object]] = []
    for block in per_source_candidates:
        if not _is_str_object_dict(block):
            continue
        block_candidates = _sanitize_candidates(block.get("candidates")) or []
        candidates.extend(dict(candidate) for candidate in block_candidates)
    answer = _answer_dict(state, "covers_policy")
    by_source_relative_path, mode, url, choice = _resolve_choice_by_source(
        selected_paths=selected_paths,
        per_source_candidates=per_source_candidates,
        answer=answer,
        state=state,
    )
    discover_answer = _answer_dict(state, "cover_discover_initial")
    allowed_modes = _allowed_modes_for_candidates(_sanitize_candidates(candidates) or [])
    if len(selected_paths) > 1 and "per_book" not in allowed_modes:
        allowed_modes.append("per_book")
    per_source_allowed_modes: list[list[str]] = []
    per_source_hints: list[str] = []
    per_source_lookup = {
        str(item.get("source_relative_path") or ""): dict(item)
        for item in per_source_candidates
        if _is_str_object_dict(item)
    }
    for source_relative_path in selected_paths:
        item = _as_str_object_dict(per_source_lookup.get(source_relative_path))
        item_candidates = _sanitize_candidates(item.get("candidates")) or []
        per_source_allowed_modes.append(_allowed_modes_for_candidates(item_candidates))
        item_error = _sanitize_error_dict(item.get("error"))
        if item_error:
            message = str(item_error.get("message") or item_error.get("type") or "failed")
            per_source_hints.append(f"{source_relative_path}: failed ({message})")
            continue
        if not item_candidates:
            per_source_hints.append(f"{source_relative_path}: none")
            continue
        kinds = ",".join(str(candidate.get("kind") or "") for candidate in item_candidates)
        per_source_hints.append(f"{source_relative_path}: {len(item_candidates)} [{kinds}]")
    return {
        "mode": mode,
        "url": url,
        "selected_source_relative_paths": selected_paths,
        "choice": choice,
        "candidates": candidates,
        "sources": per_source_candidates,
        "has_single_candidate": len(candidates) == 1,
        "by_source_relative_path": by_source_relative_path,
        "allowed_modes": allowed_modes,
        "per_source_allowed_modes": per_source_allowed_modes,
        "per_source_hints": per_source_hints,
        "discovery_summary": _build_cover_summary(
            per_source_candidates=per_source_candidates,
            error_any=discover_answer.get("error"),
        ),
    }
