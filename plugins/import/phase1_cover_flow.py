"""Deterministic cover-policy projection for PHASE 1 import sessions.

ASCII-only.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from plugins.cover_handler.plugin import CoverHandlerPlugin

_FILE_COVER_NAMES = (
    "cover.jpg",
    "cover.jpeg",
    "cover.png",
    "cover.webp",
    "folder.jpg",
    "folder.jpeg",
    "folder.png",
    "front.jpg",
    "front.png",
)
_GENERIC_COVER_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
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


def _candidate_entries(
    *,
    discovery: list[dict[str, Any]],
    source_relative_path: str,
    source_prefix: str,
    root_name: str,
) -> list[dict[str, str]]:
    plugin = CoverHandlerPlugin()
    entries: list[str] = []
    for item in discovery:
        if not isinstance(item, dict) or item.get("kind") != "file":
            continue
        rel_any = item.get("relative_path")
        if not isinstance(rel_any, str):
            continue
        rel = _normalize_relative_path(rel_path=rel_any, source_prefix=source_prefix)
        parent = str(PurePosixPath(rel).parent)
        parent = "" if parent == "." else parent
        if parent != source_relative_path:
            continue
        entries.append(rel)

    named: list[dict[str, str]] = []
    generic: list[dict[str, str]] = []
    embedded: list[str] = []
    lower_named = {name.lower() for name in _FILE_COVER_NAMES}
    for rel in sorted(entries):
        name = PurePosixPath(rel).name
        lower_name = name.lower()
        candidate = {
            "source_relative_path": source_relative_path,
            "root_name": root_name,
        }
        if lower_name in lower_named:
            named.append(
                {
                    **candidate,
                    "kind": "file",
                    "candidate_id": f"file:{lower_name}",
                    "apply_mode": "copy",
                    "path": rel,
                    "mime_type": plugin.resolve_cover_mime(path=Path(name)),
                    "cache_key": f"file:{lower_name}",
                }
            )
            continue
        if lower_name.endswith(_GENERIC_COVER_SUFFIXES):
            generic.append(
                {
                    **candidate,
                    "kind": "file",
                    "candidate_id": f"file:{lower_name}",
                    "apply_mode": "copy",
                    "path": rel,
                    "mime_type": plugin.resolve_cover_mime(path=Path(name)),
                    "cache_key": f"file:{lower_name}",
                }
            )
            continue
        if lower_name.endswith(tuple(_EMBEDDED_SUFFIXES)):
            embedded.append(rel)

    candidates = [*named, *generic]
    if embedded:
        first_audio = embedded[0]
        audio_name = PurePosixPath(first_audio).name
        candidates.append(
            {
                "source_relative_path": source_relative_path,
                "root_name": root_name,
                "kind": "embedded",
                "candidate_id": f"embedded:{audio_name}",
                "apply_mode": "extract_embedded",
                "path": first_audio,
                "mime_type": "image/jpeg",
                "cache_key": f"embedded:{audio_name.lower()}",
            }
        )
    return candidates


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


def build_phase1_cover_projection(
    *,
    discovery: list[dict[str, Any]],
    source_projection: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    selected_paths = _selected_paths(source_projection)
    source_prefix = (
        str(state.get("source", {}).get("relative_path") or "").replace("\\", "/").strip("/")
    )
    root_name = str(state.get("source", {}).get("root") or "")
    per_source_candidates = [
        {
            "source_relative_path": source_relative_path,
            "candidates": _candidate_entries(
                discovery=discovery,
                source_relative_path=source_relative_path,
                source_prefix=source_prefix,
                root_name=root_name,
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
    default_choice = _default_choice(candidates=candidates, selected_paths=selected_paths)
    answer = _answer_dict(state, "covers_policy")
    choice, mode, url = _merge_cover_answer(
        default_choice=default_choice,
        candidates=candidates,
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
    }
