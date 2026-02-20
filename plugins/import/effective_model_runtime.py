"""Runtime helpers for effective_model.json handling.

This module contains logic that must not inflate engine.py size.

ASCII-only.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from plugins.file_io.service import FileService
from plugins.file_io.service.types import RootName

from . import selection_runtime
from .fingerprints import fingerprint_json
from .storage import atomic_write_json


def needs_runtime_selection_items(effective_model: dict[str, Any]) -> bool:
    steps_any = effective_model.get("steps")
    if not isinstance(steps_any, list):
        return False

    for step in steps_any:
        if not (
            isinstance(step, dict) and step.get("step_id") in {"select_authors", "select_books"}
        ):
            continue

        fields_any = step.get("fields")
        if not isinstance(fields_any, list):
            continue

        for field in fields_any:
            if not isinstance(field, dict):
                continue
            if field.get("type") != "multi_select_indexed":
                continue
            items_any = field.get("items")
            if not (isinstance(items_any, list) and items_any):
                return True

    return False


def inject_selection_items_runtime(
    *,
    effective_model: dict[str, Any],
    authors_items: list[dict[str, str]],
    books_items: list[dict[str, str]],
) -> dict[str, Any]:
    # Runtime-only: do not mutate the dict loaded from storage.
    copied = dict(effective_model)

    steps_any = copied.get("steps")
    if not isinstance(steps_any, list):
        return copied

    copied["steps"] = [dict(s) if isinstance(s, dict) else s for s in steps_any]

    return selection_runtime.inject_selection_items(
        effective_model=copied,
        authors_items=authors_items,
        books_items=books_items,
    )


def load_effective_model_runtime(
    *,
    _fs: FileService,
    session_id: str,
    load_effective_model: Callable[[str], dict[str, Any]],
    load_discovery_snapshot: Callable[[str], list[dict[str, Any]] | None],
) -> dict[str, Any]:
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
    loaded_state: dict[str, Any],
    expected_model_fingerprint: str,
    load_effective_model: Callable[[str], dict[str, Any]],
    load_discovery_snapshot: Callable[[str], list[dict[str, Any]] | None],
    now_iso_utc: Callable[[], str],
) -> dict[str, Any]:
    """One-time upgrader for legacy sessions missing selection items.

    The upgrader only writes effective_model.json when it can deterministically
    reconstruct the expected model fingerprint.
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

    session_dir = f"import/sessions/{session_id}"
    atomic_write_json(
        fs,
        RootName.WIZARDS,
        f"{session_dir}/effective_model.json",
        upgraded_model,
    )
    loaded_state["model_fingerprint"] = expected_model_fingerprint
    loaded_state["updated_at"] = now_iso_utc()
    return loaded_state
