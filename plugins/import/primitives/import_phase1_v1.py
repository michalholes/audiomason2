"""Flow-visible import PHASE 1 runtime defaults primitive.

ASCII-only.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _object_schema(*, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {},
        "required": list(required or []),
        "description": "",
    }


REGISTRY_ENTRIES: list[dict[str, Any]] = [
    {
        "primitive_id": "import.phase1_runtime",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(required=["snapshot"]),
        "determinism_notes": "deterministic",
        "allowed_errors": [],
    }
]


def _dict_copy(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _answer_dict(state: dict[str, Any], key: str) -> dict[str, Any]:
    answers_any = state.get("answers")
    answers = dict(answers_any) if isinstance(answers_any, dict) else {}
    return _dict_copy(answers.get(key))


def _merge_defaults(defaults: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(defaults)
    for key, value in override.items():
        merged[str(key)] = deepcopy(value)
    return merged


DEFAULT_PARALLELISM = {"workers": 1}
DEFAULT_FILENAME_POLICY = {"mode": "keep", "template": "{author}/{title}"}
DEFAULT_EFFECTIVE_AUTHOR_TITLE = {"author": "", "title": ""}
DEFAULT_SKIP_PROCESSED_BOOKS = {"mode": "no", "enabled": False}
DEFAULT_RESOLVE_CONFLICTS = {"confirm": False}
DEFAULT_FINAL_CONFIRM = {"confirm_start": False}


def build_runtime_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    vars_any = state.get("vars")
    vars_obj = dict(vars_any) if isinstance(vars_any, dict) else {}
    phase1_any = vars_obj.get("phase1")
    phase1 = _dict_copy(phase1_any)
    phase2_inputs = _dict_copy(phase1.get("phase2_inputs"))
    metadata = _dict_copy(phase1.get("metadata"))
    cover = _dict_copy(phase1.get("cover"))
    policy = _dict_copy(phase1.get("policy"))

    effective_author_title = _merge_defaults(
        _merge_defaults(
            DEFAULT_EFFECTIVE_AUTHOR_TITLE,
            _dict_copy(phase1.get("effective_author_title")),
        ),
        _answer_dict(state, "effective_author_title"),
    )
    filename_policy = _merge_defaults(
        _merge_defaults(
            DEFAULT_FILENAME_POLICY,
            _dict_copy(phase1.get("filename_policy")),
        ),
        _answer_dict(state, "filename_policy"),
    )
    covers_policy = _merge_defaults(
        _dict_copy(phase2_inputs.get("covers_policy")),
        _answer_dict(state, "covers_policy"),
    )
    skip_processed_books = _merge_defaults(
        _dict_copy(phase2_inputs.get("skip_processed_books")),
        _answer_dict(state, "skip_processed_books"),
    )
    mode = str(skip_processed_books.get("mode") or "").strip().lower()
    if mode in {"yes", "no"}:
        skip_processed_books["enabled"] = mode == "yes"
    elif isinstance(skip_processed_books.get("enabled"), bool):
        skip_processed_books["mode"] = "yes" if skip_processed_books.get("enabled") else "no"
    else:
        skip_processed_books = dict(DEFAULT_SKIP_PROCESSED_BOOKS)

    id3_policy = _merge_defaults(
        _dict_copy(phase2_inputs.get("id3_policy")),
        _answer_dict(state, "id3_policy"),
    )
    audio_processing = _merge_defaults(
        _dict_copy(phase2_inputs.get("audio_processing")),
        _answer_dict(state, "audio_processing"),
    )
    publish_policy = _merge_defaults(
        _dict_copy(phase2_inputs.get("publish_policy")),
        _answer_dict(state, "publish_policy"),
    )
    delete_source_policy = _merge_defaults(
        _dict_copy(phase2_inputs.get("delete_source_policy")),
        _answer_dict(state, "delete_source_policy"),
    )
    conflict_policy = _merge_defaults(
        _dict_copy(phase2_inputs.get("conflict_policy")),
        _answer_dict(state, "conflict_policy"),
    )
    parallelism = _merge_defaults(
        _merge_defaults(DEFAULT_PARALLELISM, _dict_copy(phase1.get("parallelism"))),
        _answer_dict(state, "parallelism"),
    )
    final_summary_confirm = _merge_defaults(
        DEFAULT_FINAL_CONFIRM,
        _answer_dict(state, "final_summary_confirm"),
    )

    conflicts_any = state.get("conflicts")
    conflicts = _dict_copy(conflicts_any)
    has_conflicts = bool(conflicts.get("present")) or bool(conflicts.get("items"))
    resolve_required = str(conflict_policy.get("mode") or "ask") == "ask" and has_conflicts

    return {
        "plan_preview_batch": {
            "summary": deepcopy(_dict_copy(state.get("computed", {}).get("plan_summary"))),
            "selected_source_relative_paths": deepcopy(
                list(cover.get("selected_source_relative_paths") or [])
            ),
            "has_conflicts": has_conflicts,
        },
        "effective_author_title": effective_author_title,
        "filename_policy": filename_policy,
        "covers_policy": covers_policy,
        "skip_processed_books": skip_processed_books,
        "id3_policy": id3_policy,
        "audio_processing": audio_processing,
        "publish_policy": publish_policy,
        "delete_source_policy": delete_source_policy,
        "conflict_policy": conflict_policy,
        "parallelism": parallelism,
        "final_summary_confirm": final_summary_confirm,
        "resolve_conflicts_batch": {
            **DEFAULT_RESOLVE_CONFLICTS,
            "has_conflicts": has_conflicts,
            "required": resolve_required,
            "policy": str(conflict_policy.get("mode") or "ask"),
        },
        "phase2_inputs": deepcopy(phase2_inputs),
        "metadata": metadata,
        "cover": cover,
        "policy": policy,
    }


def execute(
    primitive_id: str,
    primitive_version: int,
    inputs: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    del inputs
    if primitive_version != 1:
        raise ValueError("unsupported primitive version")
    if primitive_id != "import.phase1_runtime":
        raise ValueError("unknown import primitive")
    return {"snapshot": build_runtime_snapshot(state)}


__all__ = ["REGISTRY_ENTRIES", "build_runtime_snapshot", "execute"]
