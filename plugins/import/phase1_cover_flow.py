"""Deterministic cover-policy projection for PHASE 1 import sessions.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from .cover_boundary import discover_cover_candidates
from .file_io_boundary import source_ref_from_state


def _answer_dict(state: dict[str, Any], key: str) -> dict[str, Any]:
    answers_any = state.get("answers")
    answers = dict(answers_any) if isinstance(answers_any, dict) else {}
    value = answers.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _selected_paths(source_projection: dict[str, Any]) -> list[str]:
    selected_any = source_projection.get("select_books")
    selected = dict(selected_any) if isinstance(selected_any, dict) else {}
    selected_paths_any = selected.get("selected_source_relative_paths")
    return (
        [item for item in selected_paths_any if isinstance(item, str)]
        if isinstance(selected_paths_any, list)
        else []
    )


def _candidate_entries(
    *,
    source_relative_path: str,
    source_prefix: str,
    root_name: str,
    state: dict[str, Any],
    fs: Any | None,
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


def _sanitize_candidates(result_any: Any) -> list[dict[str, str]] | None:
    if not isinstance(result_any, list):
        return None
    out: list[dict[str, str]] = []
    for item in result_any:
        if isinstance(item, dict):
            out.append({str(key): str(value) for key, value in item.items()})
    return out


def _sanitize_candidates_by_source(result_any: Any) -> dict[str, list[dict[str, str]]] | None:
    if not isinstance(result_any, dict):
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


def _sanitize_error_dict(error_any: Any) -> dict[str, Any] | None:
    if not isinstance(error_any, dict):
        return None
    out: dict[str, Any] = {}
    for key, value in error_any.items():
        out[str(key)] = value
    return out


def _explicit_cover_entries_from_loop_results(result_any: Any) -> list[dict[str, Any]] | None:
    if not isinstance(result_any, list):
        return None
    entries: list[dict[str, Any]] = []
    for item in result_any:
        if not isinstance(item, dict):
            continue
        subflow_any = item.get("subflow")
        subflow = dict(subflow_any) if isinstance(subflow_any, dict) else {}
        returns_any = subflow.get("returns")
        returns = dict(returns_any) if isinstance(returns_any, dict) else {}
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
    state: dict[str, Any],
) -> list[dict[str, Any]] | None:
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
    per_source_candidates: list[dict[str, Any]],
    error_any: Any,
) -> str:
    top_level_error = dict(error_any) if isinstance(error_any, dict) else {}
    if top_level_error:
        message = str(
            top_level_error.get("message")
            or top_level_error.get("type")
            or "cover discovery failed"
        )
        return f"Cover autodetection failed: {message}"
    parts: list[str] = []
    for item in per_source_candidates:
        if not isinstance(item, dict):
            continue
        source_relative_path = str(item.get("source_relative_path") or "")
        item_error = _sanitize_error_dict(item.get("error"))
        if item_error:
            message = str(item_error.get("message") or item_error.get("type") or "failed")
            parts.append(f"{source_relative_path}: failed ({message})")
            continue
        candidates_any = item.get("candidates")
        candidates = (
            [dict(candidate) for candidate in candidates_any if isinstance(candidate, dict)]
            if isinstance(candidates_any, list)
            else []
        )
        if not candidates:
            parts.append(f"{source_relative_path}: none")
            continue
        kinds = ",".join(str(candidate.get("kind") or "") for candidate in candidates)
        parts.append(f"{source_relative_path}: {len(candidates)} [{kinds}]")
    return "Cover autodetection: " + "; ".join(parts) if parts else "Cover autodetection: none"


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
    per_source_candidates: list[dict[str, Any]],
    answer: dict[str, Any],
) -> tuple[dict[str, dict[str, str]], str, str, dict[str, str]]:
    candidates_by_source = {
        str(item.get("source_relative_path") or ""): [
            dict(candidate)
            for candidate in item.get("candidates", [])
            if isinstance(candidate, dict)
        ]
        for item in per_source_candidates
        if isinstance(item, dict)
    }
    answer_choice_any = answer.get("choice")
    answer_choice = dict(answer_choice_any) if isinstance(answer_choice_any, dict) else {}
    requested_kind = str(answer_choice.get("kind") or answer.get("mode") or "").strip().lower()
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
    discovery: list[dict[str, Any]],
    source_projection: dict[str, Any],
    state: dict[str, Any],
    fs: Any | None = None,
) -> dict[str, Any]:
    del discovery
    selected_paths = _selected_paths(source_projection)
    source_prefix = (
        str(state.get("source", {}).get("relative_path") or "").replace("\\", "/").strip("/")
    )
    root_name = str(state.get("source", {}).get("root") or "")
    explicit_candidates = _explicit_cover_candidates_from_state(
        selected_paths=selected_paths,
        state=state,
    )
    if explicit_candidates is None:
        per_source_candidates: list[dict[str, Any]] = [
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
            if isinstance(item, dict)
        }
        per_source_candidates = [
            {
                "source_relative_path": source_relative_path,
                "candidates": (
                    list(explicit_by_source[source_relative_path].get("candidates") or [])
                    if source_relative_path in explicit_by_source
                    else _candidate_entries(
                        source_relative_path=source_relative_path,
                        source_prefix=source_prefix,
                        root_name=root_name,
                        state=state,
                        fs=fs,
                    )
                ),
                "error": (
                    _sanitize_error_dict(explicit_by_source[source_relative_path].get("error"))
                    if source_relative_path in explicit_by_source
                    else None
                ),
            }
            for source_relative_path in selected_paths
        ]
    candidates = [
        dict(candidate)
        for block in per_source_candidates
        for candidate in block.get("candidates", [])
        if isinstance(candidate, dict)
    ]
    answer = _answer_dict(state, "covers_policy")
    by_source_relative_path, mode, url, choice = _resolve_choice_by_source(
        selected_paths=selected_paths,
        per_source_candidates=per_source_candidates,
        answer=answer,
    )
    discover_answer = _answer_dict(state, "cover_discover_initial")
    allowed_modes = ["skip", "url"]
    candidate_kinds = {
        str(candidate.get("kind") or "") for candidate in candidates if isinstance(candidate, dict)
    }
    if "embedded" in candidate_kinds:
        allowed_modes.insert(0, "embedded")
    if "file" in candidate_kinds:
        insert_at = 1 if "embedded" in candidate_kinds else 0
        allowed_modes.insert(insert_at, "file")
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
        "discovery_summary": _build_cover_summary(
            per_source_candidates=per_source_candidates,
            error_any=discover_answer.get("error"),
        ),
    }
