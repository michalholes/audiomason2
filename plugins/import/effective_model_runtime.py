"""Runtime helpers for effective_model.json handling.

This module contains logic that must not inflate engine.py size.

ASCII-only.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeGuard

from plugins.file_io.service import FileService

from . import selection_runtime
from .fingerprints import fingerprint_json


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def needs_runtime_selection_items(effective_model: dict[str, object]) -> bool:
    steps_any = effective_model.get("steps")
    if not _is_object_list(steps_any):
        return False

    for step in steps_any:
        if not _is_str_object_dict(step):
            continue
        if step.get("step_id") not in {"select_authors", "select_books"}:
            continue

        fields_any = step.get("fields")
        if not _is_object_list(fields_any):
            continue

        for field in fields_any:
            if not _is_str_object_dict(field):
                continue
            if field.get("type") != "multi_select_indexed":
                continue
            items_any = field.get("items")
            if not (_is_object_list(items_any) and items_any):
                return True

    return False


def inject_selection_items_runtime(
    *,
    effective_model: dict[str, object],
    authors_items: list[dict[str, str]],
    books_items: list[dict[str, str]],
) -> dict[str, object]:
    # Runtime-only: do not mutate the dict loaded from storage.
    copied = dict(effective_model)

    steps_any = copied.get("steps")
    if not _is_object_list(steps_any):
        return copied

    copied["steps"] = [dict(step) for step in steps_any if _is_str_object_dict(step)]

    return selection_runtime.inject_selection_items(
        effective_model=copied,
        authors_items=authors_items,
        books_items=books_items,
    )


def load_effective_model_runtime(
    *,
    _fs: FileService,
    session_id: str,
    load_effective_model: Callable[[str], dict[str, object]],
    load_discovery_snapshot: Callable[[str], list[dict[str, object]] | None],
) -> dict[str, object]:
    """Load immutable snapshot model, then apply runtime-only enrichments."""

    effective_model = load_effective_model(session_id)
    if not isinstance(effective_model, dict):
        return effective_model

    if not needs_runtime_selection_items(effective_model):
        return effective_model

    try:
        discovery = load_discovery_snapshot(session_id)
        if discovery is None:
            return effective_model

        authors_items, books_items = selection_runtime.derive_selection_items(discovery)
        return inject_selection_items_runtime(
            effective_model=effective_model,
            authors_items=authors_items,
            books_items=books_items,
        )
    except Exception:
        return effective_model


def upgrade_legacy_selection_snapshot_if_needed(
    *,
    fs: FileService,
    session_id: str,
    loaded_state: dict[str, object],
    expected_model_fingerprint: str,
    load_effective_model: Callable[[str], dict[str, object]],
    load_discovery_snapshot: Callable[[str], list[dict[str, object]] | None],
    now_iso_utc: Callable[[], str],
) -> dict[str, object]:
    """One-time upgrader for legacy sessions missing selection items.

    Immutable snapshot rule (spec 10.9): effective_model.json must never be
    rewritten after session creation. If we can deterministically reconstruct
    the runtime model, repair state only.
    """

    current_fp = str(loaded_state.get("model_fingerprint") or "")
    if not current_fp or current_fp == expected_model_fingerprint:
        return loaded_state

    try:
        effective_model = load_effective_model(session_id)
    except Exception:
        return loaded_state

    if not isinstance(effective_model, dict):
        return loaded_state

    try:
        on_disk_fp = fingerprint_json(effective_model)
    except Exception:
        return loaded_state

    if on_disk_fp != current_fp:
        return loaded_state

    discovery = load_discovery_snapshot(session_id)
    if discovery is None:
        return loaded_state

    try:
        authors_items, books_items = selection_runtime.derive_selection_items(discovery)
        upgraded_model = selection_runtime.inject_selection_items(
            effective_model=dict(effective_model),
            authors_items=authors_items,
            books_items=books_items,
        )
    except Exception:
        return loaded_state

    try:
        upgraded_fp = fingerprint_json(upgraded_model)
    except Exception:
        return loaded_state

    if upgraded_fp != expected_model_fingerprint:
        return loaded_state

    # Do not persist upgraded_model. Snapshot is immutable.
    loaded_state["model_fingerprint"] = expected_model_fingerprint
    loaded_state["updated_at"] = now_iso_utc()
    return loaded_state
