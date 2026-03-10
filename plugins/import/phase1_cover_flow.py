"""Deterministic cover-policy projection for PHASE 1 import sessions.

ASCII-only.
"""

from __future__ import annotations

from typing import Any


def _answer_dict(state: dict[str, Any], key: str) -> dict[str, Any]:
    answers_any = state.get("answers")
    answers = dict(answers_any) if isinstance(answers_any, dict) else {}
    value = answers.get(key)
    return dict(value) if isinstance(value, dict) else {}


def build_phase1_cover_projection(
    *,
    source_projection: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    selected_any = source_projection.get("select_books")
    selected = dict(selected_any) if isinstance(selected_any, dict) else {}
    selected_paths_any = selected.get("selected_source_relative_paths")
    selected_paths = (
        [item for item in selected_paths_any if isinstance(item, str)]
        if isinstance(selected_paths_any, list)
        else []
    )
    default_mode = "embedded" if len(selected_paths) == 1 else "skip"
    cover = {
        "mode": default_mode,
        "url": "",
        "selected_source_relative_paths": selected_paths,
        "choice": default_mode,
        "has_single_candidate": len(selected_paths) == 1,
    }
    cover.update(_answer_dict(state, "covers_policy"))
    return cover
