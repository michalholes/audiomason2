"""Import engine conflict helpers.

This module is intentionally small and pure: it operates on the session state
dict and uses engine IO for persistence only.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from plugins.file_io.service.types import RootName

from .engine_util import _iso_utc_now
from .errors import StepSubmissionError
from .storage import atomic_write_json


def apply_conflict_policy(*, state: dict[str, Any], payload: dict[str, Any]) -> None:
    raw_mode = payload.get("mode")
    if not isinstance(raw_mode, str) or not raw_mode.strip():
        raise StepSubmissionError("conflict_policy.mode must be a non-empty string")
    mode = raw_mode.strip().lower()
    try:
        mode.encode("ascii")
    except UnicodeEncodeError as e:
        raise StepSubmissionError("conflict_policy.mode must be ASCII-only") from e

    policy = "ask" if mode == "ask" else mode

    conflicts = state.get("conflicts")
    conflicts = conflicts if isinstance(conflicts, dict) else {}

    conflicts["policy"] = policy

    items = conflicts.get("items")
    present = bool(conflicts.get("present"))
    if isinstance(items, list):
        present = present or bool(items)

    if policy != "ask":
        conflicts["resolved"] = True
    else:
        conflicts["resolved"] = bool(conflicts.get("resolved")) if present else True

    state["conflicts"] = conflicts


def apply_conflict_resolve(*, state: dict[str, Any], payload: dict[str, Any]) -> None:
    conflicts = state.get("conflicts")
    if not isinstance(conflicts, dict):
        raise StepSubmissionError("conflicts missing from state")

    policy = str(conflicts.get("policy") or "ask")
    if policy != "ask":
        conflicts["resolved"] = True
        state["conflicts"] = conflicts
        return

    confirm = payload.get("confirm")
    if confirm is not True:
        raise StepSubmissionError("resolve_conflicts_batch.confirm must be true")

    conflicts["resolved"] = True
    state["conflicts"] = conflicts


def persist_conflict_resolution(
    *,
    engine: Any,
    session_id: str,
    state: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    conflicts = state.get("conflicts")
    if not isinstance(conflicts, dict):
        return
    record = {
        "at": _iso_utc_now(),
        "policy": str(conflicts.get("policy") or ""),
        "conflict_fingerprint": str(state.get("derived", {}).get("conflict_fingerprint") or ""),
        "payload": dict(payload),
    }
    session_dir = f"import/sessions/{session_id}"
    atomic_write_json(
        engine.get_file_service(),
        RootName.WIZARDS,
        f"{session_dir}/conflicts_resolution.json",
        record,
    )
