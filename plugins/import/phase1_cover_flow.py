"""Deterministic cover-policy projection for PHASE 1 import sessions.

ASCII-only.
"""

from __future__ import annotations

from typing import Any


def build_phase1_cover_projection(*, source_projection: dict[str, Any]) -> dict[str, Any]:
    selected_any = source_projection.get("select_books")
    selected = dict(selected_any) if isinstance(selected_any, dict) else {}
    selected_paths_any = selected.get("selected_source_relative_paths")
    selected_paths = (
        [item for item in selected_paths_any if isinstance(item, str)]
        if isinstance(selected_paths_any, list)
        else []
    )
    return {
        "mode": "skip",
        "url": "",
        "selected_source_relative_paths": selected_paths,
        "choice": "skip",
    }
