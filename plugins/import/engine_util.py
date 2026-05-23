"""Import engine utility helpers (plugin: import).

Extracted from engine.py to satisfy anti-monolith gate.

ASCII-only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypeGuard

from .engine_diagnostics_required import emit_required
from .errors import (
    FinalizeError,
    ImportWizardError,
    ModelValidationError,
    SessionNotFoundError,
    StepSubmissionError,
    error_envelope,
    invariant_violation,
    validation_error,
)
from .field_schema_validation import FieldSchemaValidationError
from .fingerprints import sha256_hex


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _selection_item_sort_key(item: dict[str, str]) -> tuple[str, str]:
    return (item.get("label", ""), item.get("item_id", ""))


def _to_ascii(text: str) -> str:
    return text.encode("ascii", errors="replace").decode("ascii")


def _derive_selection_items(
    discovery: list[dict[str, object]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    authors: dict[str, dict[str, str]] = {}
    books: dict[str, dict[str, str]] = {}

    dirs: list[str] = []
    for it in discovery:
        if not (_is_str_object_dict(it) and it.get("kind") == "dir"):
            continue
        rel_any = it.get("relative_path")
        if not isinstance(rel_any, str):
            continue
        dirs.append(rel_any.replace("\\", "/"))

    pairs: set[tuple[str, str]] = set()
    for rel in dirs:
        segs = [s for s in rel.split("/") if s]
        if len(segs) >= 2:
            pairs.add((segs[0], segs[1]))

    if not pairs:
        for rel in dirs:
            segs = [s for s in rel.split("/") if s]
            if segs:
                pairs.add((segs[0], segs[0]))

    if not pairs:
        pairs.add(("(root)", "(root)"))

    for author_key, book_key in sorted(pairs):
        author_label = _to_ascii(author_key)
        label = author_key if author_key == book_key else f"{author_key} / {book_key}"
        book_label = _to_ascii(label)

        author_id = "author:" + sha256_hex(f"a|{author_key}".encode())[:16]
        book_id = "book:" + sha256_hex(f"b|{author_key}|{book_key}".encode())[:16]

        authors.setdefault(
            author_id,
            {"item_id": author_id, "label": author_label, "display_label": author_key},
        )
        books.setdefault(
            book_id,
            {"item_id": book_id, "label": book_label, "display_label": label},
        )

    authors_items = sorted(list(authors.values()), key=_selection_item_sort_key)
    books_items = sorted(list(books.values()), key=_selection_item_sort_key)
    return authors_items, books_items


def _inject_selection_items(
    *,
    effective_model: dict[str, object],
    authors_items: list[dict[str, str]],
    books_items: list[dict[str, str]],
) -> dict[str, object]:
    steps_any = effective_model.get("steps")
    if not _is_object_list(steps_any):
        return effective_model

    steps: list[dict[str, object]] = [dict(step) for step in steps_any if _is_str_object_dict(step)]
    for step in steps:
        step_id = step.get("step_id")
        if step_id not in {"select_authors", "select_books"}:
            continue
        fields_any = step.get("fields")
        if not _is_object_list(fields_any):
            continue
        fields: list[dict[str, object]] = [
            dict(field) for field in fields_any if _is_str_object_dict(field)
        ]
        for fld in fields:
            if fld.get("type") != "multi_select_indexed":
                continue
            fld["items"] = list(authors_items if step_id == "select_authors" else books_items)

    effective_model["steps"] = steps
    return effective_model


def _emit_required(event: str, operation: str, data: dict[str, object]) -> None:
    required_ctx: dict[str, object] = {}
    for key in [
        "session_id",
        "model_fingerprint",
        "discovery_fingerprint",
        "effective_config_fingerprint",
    ]:
        if key in data and data.get(key) is not None:
            required_ctx[key] = data.get(key)
    emit_required(event=event, operation=operation, data=data, required_ctx=required_ctx)


def _iso_utc_now() -> str:
    # RFC3339 / ISO-8601 in UTC (Z suffix).
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sync_session_cursor(
    state: dict[str, object], *, step_id: str | None = None
) -> dict[str, object]:
    cursor_any = state.get("cursor")
    cursor = _as_str_object_dict(cursor_any)
    if step_id is None:
        step_id = str(state.get("current_step_id") or cursor.get("step_id") or "")
    cursor["step_id"] = str(step_id or "")
    state["cursor"] = cursor
    if step_id:
        state["current_step_id"] = str(step_id)
    return state


MAX_TRACE_EVENTS = 1000


def append_trace_event(state: dict[str, object], event: dict[str, object]) -> dict[str, object]:
    trace_any = state.get("trace")
    trace = [item for item in trace_any] if _is_object_list(trace_any) else []
    item = dict(event)
    item["seq"] = len(trace) + 1
    trace.append(item)
    if len(trace) > MAX_TRACE_EVENTS:
        trace = trace[-MAX_TRACE_EVENTS:]
        for idx, trace_item in enumerate(trace, start=1):
            if isinstance(trace_item, dict):
                trace_item["seq"] = idx
    state["trace"] = trace
    return state


def _ensure_session_state_fields(state: dict[str, object]) -> dict[str, object]:
    """Ensure SessionState contains minimally required fields (spec 10.*).

    This is a backward-compatible upgrader for existing sessions.
    """
    changed = False

    def _setdefault(key: str, value: object) -> None:
        nonlocal changed
        if key not in state:
            state[key] = value
            changed = True

    _setdefault("session_state_version", 1)
    _setdefault("status", "in_progress")
    _setdefault("answers", {})
    _setdefault("vars", {})
    _setdefault("jobs", {"emitted": [], "submitted": []})
    _setdefault("trace", [])
    _setdefault("computed", {})
    _setdefault("selected_author_ids", [])
    _setdefault("selected_book_ids", [])
    _setdefault("effective_author_title", {})

    # Backward compatibility: keep legacy inputs but answers is canonical.
    if "inputs" not in state:
        state["inputs"] = {}
        changed = True

    answers_any = state.get("answers")
    inputs_any = state.get("inputs")

    if (
        _is_str_object_dict(answers_any)
        and not answers_any
        and _is_str_object_dict(inputs_any)
        and inputs_any
    ):
        state["answers"] = dict(inputs_any)
        changed = True

    sync_session_cursor(state)

    jobs_any = state.get("jobs")
    jobs = _as_str_object_dict(jobs_any)
    if "emitted" not in jobs or not _is_object_list(jobs.get("emitted")):
        jobs["emitted"] = []
        changed = True
    if "submitted" not in jobs or not _is_object_list(jobs.get("submitted")):
        jobs["submitted"] = []
        changed = True
    state["jobs"] = jobs

    if changed:
        state["updated_at"] = _iso_utc_now()
    return state


def _exception_envelope(exc: Exception) -> dict[str, object]:
    if isinstance(exc, SessionNotFoundError):
        return error_envelope(
            "NOT_FOUND",
            str(exc) or "not found",
            details=[{"path": "$.session_id", "reason": "not_found", "meta": {}}],
        )
    if isinstance(exc, FieldSchemaValidationError):
        return validation_error(
            message=str(exc) or "validation error",
            path=str(exc.path) or "$",
            reason=str(exc.reason) or "validation_error",
            meta=dict(exc.meta),
        )
    if isinstance(exc, (StepSubmissionError, ValueError)):
        return validation_error(
            message=str(exc) or "validation error",
            path="$",
            reason="validation_error",
            meta={"type": exc.__class__.__name__},
        )
    if isinstance(exc, FinalizeError):
        return invariant_violation(
            message=str(exc) or "invariant violation",
            path="$",
            reason="invariant_violation",
            meta={"type": exc.__class__.__name__},
        )
    if isinstance(exc, ModelValidationError):
        return invariant_violation(
            message=str(exc) or "invariant violation",
            path="$",
            reason="invariant_violation",
            meta={"type": exc.__class__.__name__},
        )
    if isinstance(exc, ImportWizardError):
        return error_envelope(
            "INTERNAL_ERROR",
            str(exc) or "internal error",
            details=[
                {
                    "path": "$.error",
                    "reason": "internal_error",
                    "meta": {"type": exc.__class__.__name__},
                }
            ],
        )
    return error_envelope(
        "INTERNAL_ERROR",
        str(exc) or "internal error",
        details=[
            {
                "path": "$.error",
                "reason": "internal_error",
                "meta": {"type": exc.__class__.__name__},
            }
        ],
    )


def _parse_selection_expr(expr: str, *, max_index: int | None) -> list[int]:
    text = expr.strip().lower()
    if text == "all":
        if max_index is None:
            # Caller must provide max_index to expand "all".
            raise ValueError("selection 'all' requires a known max_index")
        return list(range(1, max_index + 1))

    ids: set[int] = set()
    for raw in text.split(","):
        tok = raw.strip()
        if not tok:
            continue
        if "-" in tok:
            parts = [p.strip() for p in tok.split("-", 1)]
            if len(parts) != 2 or not parts[0] or not parts[1]:
                raise ValueError(f"invalid range token: {tok}")
            try:
                start = int(parts[0])
                end = int(parts[1])
            except ValueError as e:
                raise ValueError(f"invalid range token: {tok}") from e
            if start <= 0 or end <= 0 or end < start:
                raise ValueError(f"invalid range token: {tok}")
            for i in range(start, end + 1):
                ids.add(i)
        else:
            try:
                i = int(tok)
            except ValueError as e:
                raise ValueError(f"invalid selection token: {tok}") from e
            if i <= 0:
                raise ValueError(f"invalid selection token: {tok}")
            ids.add(i)

    result = sorted(ids)
    if max_index is not None and any(i > max_index for i in result):
        raise ValueError("selection out of range")
    return result
