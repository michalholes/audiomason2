"""Deterministic policy projection for PHASE 1 import sessions.

ASCII-only.
"""

from __future__ import annotations

from copy import deepcopy
from typing import TypeGuard, cast

DEFAULT_AUDIO_POLICY: dict[str, object] = {
    "bitrate": "128k",
    "loudnorm": False,
    "split_chapters": False,
}
DEFAULT_PARALLELISM: dict[str, object] = {"workers": 1}
DEFAULT_SKIP_PROCESSED_BOOKS: dict[str, object] = {"mode": "no", "enabled": False}
_ROOT_AUDIO_BASELINE: dict[str, object] = {"author": "__ROOT_AUDIO__", "title": "Untitled"}


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_str_list(value: object) -> list[str]:
    if not _is_object_list(value):
        return []
    return [item for item in value if isinstance(item, str)]


def _answer_dict(state: dict[str, object], key: str) -> dict[str, object]:
    answers = _as_str_object_dict(state.get("answers"))
    value = answers.get(key)
    return _as_str_object_dict(value)


def _normalize_clean_inbox(answer: dict[str, object]) -> str:
    clean_inbox = str(answer.get("clean_inbox") or "").strip().lower()
    if clean_inbox in {"ask", "yes", "no"}:
        return clean_inbox
    enabled = answer.get("enabled")
    if isinstance(enabled, bool):
        return "yes" if enabled else "no"
    mode = str(answer.get("mode") or "").strip().lower()
    if mode in {"ask", "delete", "drop", "remove"}:
        return "yes" if mode in {"delete", "drop", "remove"} else "ask"
    if mode in {"keep", "no"}:
        return "no"
    return "ask"


def _normalize_skip_processed_books(answer: dict[str, object]) -> dict[str, object]:
    mode = str(answer.get("mode") or "").strip().lower()
    if mode in {"yes", "no"}:
        return {"mode": mode, "enabled": mode == "yes"}
    enabled = answer.get("enabled")
    if isinstance(enabled, bool):
        return {"mode": "yes" if enabled else "no", "enabled": enabled}
    return dict(DEFAULT_SKIP_PROCESSED_BOOKS)


def build_phase1_policy_projection(
    *,
    state: dict[str, object],
    source_projection: dict[str, object],
) -> dict[str, object]:
    mode = str(state.get("mode") or "stage")
    target_root = "stage" if mode == "stage" else "outbox"
    selected = _as_str_object_dict(source_projection.get("select_books"))
    selected_count = len(_as_str_list(selected.get("selected_ids")))

    conflict_policy: dict[str, object] = {"mode": "ask"}
    conflict_policy.update(_answer_dict(state, "conflict_policy"))

    audio_processing: dict[str, object] = deepcopy(DEFAULT_AUDIO_POLICY)
    audio_processing.update(_answer_dict(state, "audio_processing"))

    publish_policy: dict[str, object] = {"target_root": target_root}
    publish_policy.update(_answer_dict(state, "publish_policy"))

    delete_source_answer = _answer_dict(state, "delete_source_policy")
    clean_inbox = _normalize_clean_inbox(delete_source_answer)
    delete_source_policy: dict[str, object] = {
        "clean_inbox": clean_inbox,
        "enabled": clean_inbox == "yes",
        "mode": "delete" if clean_inbox == "yes" else ("keep" if clean_inbox == "no" else "ask"),
    }
    delete_source_policy.update(delete_source_answer)
    delete_source_policy["clean_inbox"] = clean_inbox
    delete_source_policy["enabled"] = clean_inbox == "yes"
    delete_source_policy["mode"] = (
        "delete" if clean_inbox == "yes" else ("keep" if clean_inbox == "no" else "ask")
    )

    parallelism: dict[str, object] = deepcopy(DEFAULT_PARALLELISM)
    parallelism.update(_answer_dict(state, "parallelism"))

    skip_processed_books_policy = _normalize_skip_processed_books(
        _answer_dict(state, "skip_processed_books")
    )

    return {
        "conflict_policy": conflict_policy,
        "audio_processing": audio_processing,
        "publish_policy": publish_policy,
        "delete_source_policy": delete_source_policy,
        "parallelism": parallelism,
        "skip_processed_books_policy": skip_processed_books_policy,
        "clean_inbox": clean_inbox,
        "skip_processed_books": bool(skip_processed_books_policy.get("enabled", False)),
        "root_audio_baseline": {
            **_ROOT_AUDIO_BASELINE,
            "target_root": str(publish_policy.get("target_root") or target_root),
            "selected_books": selected_count,
        },
        "two_pass_order": [
            "select_authors",
            "select_books",
            "plan_preview_batch",
            "effective_author_title",
            "filename_policy",
            "covers_policy",
            "id3_policy",
            "audio_processing",
            "publish_policy",
            "delete_source_policy",
            "skip_processed_books",
            "conflict_policy",
            "parallelism",
            "final_summary_confirm",
        ],
    }
