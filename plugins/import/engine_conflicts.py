"""Import engine conflict helpers.

This module is intentionally small and pure: it operates on the session state
dict and uses engine IO for persistence only.

ASCII-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeGuard, cast

from plugins.file_io.service.types import RootName

from .engine_util import iso_utc_now
from .errors import StepSubmissionError
from .storage import atomic_write_json

if TYPE_CHECKING:
    from .engine import ImportWizardEngine


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def apply_conflict_policy(*, state: dict[str, object], payload: dict[str, object]) -> None:
    raw_mode = payload.get("mode")
    if not isinstance(raw_mode, str) or not raw_mode.strip():
        raise StepSubmissionError("conflict_policy.mode must be a non-empty string")
    mode = raw_mode.strip().lower()
    try:
        mode.encode("ascii")
    except UnicodeEncodeError as e:
        raise StepSubmissionError("conflict_policy.mode must be ASCII-only") from e

    policy = "ask" if mode == "ask" else mode

    conflicts = _as_str_object_dict(state.get("conflicts"))

    conflicts["policy"] = policy

    items = conflicts.get("items")
    present = bool(conflicts.get("present"))
    if _is_object_list(items):
        present = present or bool(items)

    if policy != "ask":
        conflicts["resolved"] = True
    else:
        conflicts["resolved"] = bool(conflicts.get("resolved")) if present else True

    state["conflicts"] = conflicts


def apply_conflict_resolve(*, state: dict[str, object], payload: dict[str, object]) -> None:
    conflicts = state.get("conflicts")
    if not _is_str_object_dict(conflicts):
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
    engine: ImportWizardEngine,
    session_id: str,
    state: dict[str, object],
    payload: dict[str, object],
) -> None:
    conflicts = state.get("conflicts")
    if not _is_str_object_dict(conflicts):
        return
    derived = _as_str_object_dict(state.get("derived"))
    record = {
        "at": iso_utc_now(),
        "policy": str(conflicts.get("policy") or ""),
        "conflict_fingerprint": str(derived.get("conflict_fingerprint") or ""),
        "payload": dict(payload),
    }
    session_dir = f"import/sessions/{session_id}"
    atomic_write_json(
        engine.get_file_service(),
        RootName.WIZARDS,
        f"{session_dir}/conflicts_resolution.json",
        record,
    )
