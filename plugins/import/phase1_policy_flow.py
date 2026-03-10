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


def _answer_dict(state: dict[str, Any], key: str) -> dict[str, Any]:
    answers_any = state.get("answers")
    answers = dict(answers_any) if isinstance(answers_any, dict) else {}
    value = answers.get(key)
    return dict(value) if isinstance(value, dict) else {}


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

    delete_source_policy = {"enabled": False, "mode": "keep"}
    delete_source_policy.update(_answer_dict(state, "delete_source_policy"))

    parallelism = deepcopy(DEFAULT_PARALLELISM)
    parallelism.update(_answer_dict(state, "parallelism"))

    return {
        "conflict_policy": conflict_policy,
        "audio_processing": audio_processing,
        "publish_policy": publish_policy,
        "delete_source_policy": delete_source_policy,
        "parallelism": parallelism,
        "clean_inbox": bool(delete_source_policy.get("enabled", False)),
        "skip_processed_books": str(conflict_policy.get("mode") or "ask") == "skip",
        "root_audio_baseline": {
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
            "conflict_policy",
            "parallelism",
            "final_summary_confirm",
        ],
    }
