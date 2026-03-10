"""Deterministic policy projection for PHASE 1 import sessions.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

DEFAULT_AUDIO_POLICY = {
    "bitrate": "128k",
    "loudnorm": False,
    "split_chapters": False,
}


def build_phase1_policy_projection(*, state: dict[str, Any]) -> dict[str, Any]:
    mode = str(state.get("mode") or "stage")
    target_root = "stage" if mode == "stage" else "outbox"
    return {
        "conflict_policy": {"mode": "ask"},
        "audio_processing": dict(DEFAULT_AUDIO_POLICY),
        "publish_policy": {"target_root": target_root},
        "delete_source_policy": {"enabled": False},
        "clean_inbox": False,
        "skip_processed_books": True,
        "root_audio_baseline": {"target_root": target_root},
        "two_pass_order": ["select_authors", "select_books"],
    }
