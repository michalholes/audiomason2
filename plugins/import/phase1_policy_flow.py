"""Deterministic policy projection for PHASE 1 import sessions.

ASCII-only.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

DEFAULT_AUDIO_POLICY = {
    "bitrate": "128k",
    "loudnorm": False,
    "split_chapters": False,
}
DEFAULT_PARALLELISM = {"workers": 1}
DEFAULT_SKIP_PROCESSED_BOOKS = {"mode": "no", "enabled": False}
_ROOT_AUDIO_BASELINE = {"author": "__ROOT_AUDIO__", "title": "Untitled"}


def _answer_dict(state: dict[str, Any], key: str) -> dict[str, Any]:
    answers_any = state.get("answers")
    answers = dict(answers_any) if isinstance(answers_any, dict) else {}
    value = answers.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _normalize_clean_inbox(answer: dict[str, Any]) -> str:
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


def _normalize_skip_processed_books(answer: dict[str, Any]) -> dict[str, Any]:
    mode = str(answer.get("mode") or "").strip().lower()
    if mode in {"yes", "no"}:
        return {"mode": mode, "enabled": mode == "yes"}
    enabled = answer.get("enabled")
    if isinstance(enabled, bool):
        return {"mode": "yes" if enabled else "no", "enabled": enabled}
    return dict(DEFAULT_SKIP_PROCESSED_BOOKS)


def build_phase1_policy_projection(
    *,
    state: dict[str, Any],
    source_projection: dict[str, Any],
) -> dict[str, Any]:
    mode = str(state.get("mode") or "stage")
    target_root = "stage" if mode == "stage" else "outbox"
    selected_any = source_projection.get("select_books")
    selected = dict(selected_any) if isinstance(selected_any, dict) else {}
    selected_ids_any = selected.get("selected_ids")
    selected_count = len(selected_ids_any) if isinstance(selected_ids_any, list) else 0

    conflict_policy = {"mode": "ask"}
    conflict_policy.update(_answer_dict(state, "conflict_policy"))

    audio_processing = deepcopy(DEFAULT_AUDIO_POLICY)
    audio_processing.update(_answer_dict(state, "audio_processing"))

    publish_policy = {"target_root": target_root}
    publish_policy.update(_answer_dict(state, "publish_policy"))

    delete_source_answer = _answer_dict(state, "delete_source_policy")
    clean_inbox = _normalize_clean_inbox(delete_source_answer)
    delete_source_policy = {
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

    parallelism = deepcopy(DEFAULT_PARALLELISM)
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
