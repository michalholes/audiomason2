"""Plan computation for import wizard engine.

This is a minimal baseline planner.

ASCII-only.
"""

from __future__ import annotations

from typing import Any


def compute_plan(
    *,
    session_id: str,
    root: str,
    relative_path: str,
    discovery: list[dict[str, Any]],
    inputs: dict[str, Any],
) -> dict[str, Any]:
    files = sum(1 for it in discovery if it.get("kind") == "file")
    dirs = sum(1 for it in discovery if it.get("kind") == "dir")
    bundles = sum(1 for it in discovery if it.get("kind") == "bundle")

    selected = {
        "filename_policy": inputs.get("filename_policy"),
        "covers_policy": inputs.get("covers_policy"),
        "id3_policy": inputs.get("id3_policy"),
        "audio_processing": inputs.get("audio_processing"),
        "publish_policy": inputs.get("publish_policy"),
        "delete_source_policy": inputs.get("delete_source_policy"),
        "conflict_policy": inputs.get("conflict_policy"),
        "parallelism": inputs.get("parallelism"),
    }

    return {
        "version": "0.1.0",
        "session_id": session_id,
        "source": {"root": root, "relative_path": relative_path},
        "summary": {
            "items": len(discovery),
            "files": files,
            "dirs": dirs,
            "bundles": bundles,
        },
        "selected_policies": selected,
    }
