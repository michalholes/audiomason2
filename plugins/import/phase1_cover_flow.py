"""Deterministic cover-policy projection for PHASE 1 import sessions.

ASCII-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from plugins.cover_handler.plugin import CoverHandlerPlugin

_EMBEDDED_SUFFIXES = {".mp3", ".m4a", ".m4b"}


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


def _normalize_relative_path(*, rel_path: str, source_prefix: str) -> str:
    normalized = rel_path.replace("\\", "/").strip("/")
    if not source_prefix:
        return normalized
    if normalized == source_prefix:
        return ""
    prefix = source_prefix + "/"
    if normalized.startswith(prefix):
        return normalized[len(prefix) :]
    return normalized


def _source_root_dir(state: dict[str, Any]) -> Path | None:
    source_any = state.get("source")
    source = dict(source_any) if isinstance(source_any, dict) else {}
    root_dir = str(source.get("root_dir") or "")
    return Path(root_dir) if root_dir else None


def _source_directory(
    *,
    root_dir: Path | None,
    source_prefix: str,
    source_relative_path: str,
) -> Path | None:
    if root_dir is None:
        return None
    rel_parts = [part for part in (source_prefix, source_relative_path) if part]
    rel = "/".join(rel_parts)
    return root_dir / Path(*[part for part in rel.split("/") if part])


def _first_audio_source(directory: Path) -> Path | None:
    if not directory.exists() or not directory.is_dir():
        return None
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in _EMBEDDED_SUFFIXES:
            return path
    return None


def _root_relative_path(*, root_dir: Path, path_text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    if not path.is_absolute():
        path = root_dir / path
    return path.resolve().relative_to(root_dir.resolve()).as_posix()


def _canonicalize_candidate(
    *,
    candidate: dict[str, Any],
    root_dir: Path,
    source_relative_path: str,
    root_name: str,
) -> dict[str, str]:
    out = {
        "source_relative_path": source_relative_path,
        "root_name": str(candidate.get("root_name") or root_name),
        "kind": str(candidate.get("kind") or ""),
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "apply_mode": str(candidate.get("apply_mode") or ""),
        "mime_type": str(candidate.get("mime_type") or ""),
        "cache_key": str(candidate.get("cache_key") or ""),
    }
    path_text = str(candidate.get("path") or "")
    if path_text:
        out["path"] = _root_relative_path(root_dir=root_dir, path_text=path_text)
    url = str(candidate.get("url") or "")
    if url:
        out["url"] = url
    return out


def _candidate_entries(
    *,
    source_relative_path: str,
    source_prefix: str,
    root_name: str,
    state: dict[str, Any],
) -> list[dict[str, str]]:
    root_dir = _source_root_dir(state)
    source_directory = _source_directory(
        root_dir=root_dir,
        source_prefix=source_prefix,
        source_relative_path=source_relative_path,
    )
    if root_dir is None or source_directory is None:
        return []

    plugin = CoverHandlerPlugin()
    candidates = plugin.discover_cover_candidates(
        source_directory,
        audio_file=_first_audio_source(source_directory),
        group_root=root_name,
    )
    return [
        _canonicalize_candidate(
            candidate=dict(candidate),
            root_dir=root_dir,
            source_relative_path=source_relative_path,
            root_name=root_name,
        )
        for candidate in candidates
        if isinstance(candidate, dict)
    ]


def _default_choice(candidates: list[dict[str, str]], selected_paths: list[str]) -> dict[str, str]:
    if len(selected_paths) == 1 and candidates:
        chosen = candidates[0]
        return {
            "kind": "candidate",
            "candidate_id": str(chosen.get("candidate_id") or ""),
            "source_relative_path": str(chosen.get("source_relative_path") or ""),
        }
    return {"kind": "skip"}


def _merge_cover_answer(
    *,
    default_choice: dict[str, str],
    candidates: list[dict[str, str]],
    answer: dict[str, Any],
) -> tuple[dict[str, str], str, str]:
    candidate_ids = {
        (str(item.get("candidate_id") or ""), str(item.get("source_relative_path") or ""))
        for item in candidates
    }
    default_candidate_id = str(default_choice.get("candidate_id") or "")
    default_source_relative_path = str(default_choice.get("source_relative_path") or "")

    answer_choice_any = answer.get("choice")
    answer_choice = dict(answer_choice_any) if isinstance(answer_choice_any, dict) else {}
    answer_kind = str(
        answer_choice.get("kind") or answer.get("mode") or default_choice.get("kind") or "skip"
    )
    answer_url = str(answer.get("url") or answer_choice.get("url") or "")
    answer_candidate_id = str(
        answer_choice.get("candidate_id") or answer.get("candidate_id") or default_candidate_id
    )
    answer_source_relative_path = str(
        answer_choice.get("source_relative_path")
        or answer.get("source_relative_path")
        or default_source_relative_path
    )

    if answer_kind == "url" and answer_url:
        return ({"kind": "url", "url": answer_url}, "url", answer_url)
    if (answer_candidate_id, answer_source_relative_path) in candidate_ids:
        match = next(
            item
            for item in candidates
            if str(item.get("candidate_id") or "") == answer_candidate_id
            and str(item.get("source_relative_path") or "") == answer_source_relative_path
        )
        return (
            {
                "kind": "candidate",
                "candidate_id": answer_candidate_id,
                "source_relative_path": answer_source_relative_path,
            },
            str(match.get("kind") or "skip"),
            "",
        )
    return ({"kind": "skip"}, "skip", "")


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
) -> dict[str, Any]:
    del discovery
    selected_paths = _selected_paths(source_projection)
    source_prefix = (
        str(state.get("source", {}).get("relative_path") or "").replace("\\", "/").strip("/")
    )
    root_name = str(state.get("source", {}).get("root") or "")
    per_source_candidates = [
        {
            "source_relative_path": source_relative_path,
            "candidates": _candidate_entries(
                source_relative_path=source_relative_path,
                source_prefix=source_prefix,
                root_name=root_name,
                state=state,
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
    return {
        "mode": mode,
        "url": url,
        "selected_source_relative_paths": selected_paths,
        "choice": choice,
        "candidates": candidates,
        "sources": per_source_candidates,
        "has_single_candidate": len(candidates) == 1,
        "by_source_relative_path": by_source_relative_path,
    }
