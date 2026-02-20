"""Import engine utility helpers (plugin: import).

Extracted from engine.py to satisfy anti-monolith gate.

ASCII-only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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
from .fingerprints import sha256_hex


def _to_ascii(text: str) -> str:
    return text.encode("ascii", errors="replace").decode("ascii")


def _derive_selection_items(
    discovery: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    authors: dict[str, dict[str, str]] = {}
    books: dict[str, dict[str, str]] = {}

    dirs: list[str] = []
    for it in discovery:
        if not (isinstance(it, dict) and it.get("kind") == "dir"):
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

        authors.setdefault(author_id, {"item_id": author_id, "label": author_label})
        books.setdefault(book_id, {"item_id": book_id, "label": book_label})

    authors_items = sorted(authors.values(), key=lambda x: (x["label"], x["item_id"]))
    books_items = sorted(books.values(), key=lambda x: (x["label"], x["item_id"]))
    return authors_items, books_items


def _inject_selection_items(
    *,
    effective_model: dict[str, Any],
    authors_items: list[dict[str, str]],
    books_items: list[dict[str, str]],
) -> dict[str, Any]:
    steps_any = effective_model.get("steps")
    if not isinstance(steps_any, list):
        return effective_model

    steps: list[dict[str, Any]] = [s for s in steps_any if isinstance(s, dict)]
    for step in steps:
        step_id = step.get("step_id")
        if step_id not in {"select_authors", "select_books"}:
            continue
        fields_any = step.get("fields")
        if not isinstance(fields_any, list):
            continue
        fields: list[dict[str, Any]] = [f for f in fields_any if isinstance(f, dict)]
        for fld in fields:
            if fld.get("type") != "multi_select_indexed":
                continue
            fld["items"] = list(authors_items if step_id == "select_authors" else books_items)

    effective_model["steps"] = steps
    return effective_model


def _emit_required(event: str, operation: str, data: dict[str, Any]) -> None:
    required_ctx: dict[str, Any] = {}
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


def _ensure_session_state_fields(state: dict[str, Any]) -> dict[str, Any]:
    """Ensure SessionState contains minimally required fields (spec 10.*).

    This is a backward-compatible upgrader for existing sessions.
    """
    changed = False

    def _setdefault(key: str, value: Any) -> None:
        nonlocal changed
        if key not in state:
            state[key] = value
            changed = True

    _setdefault("answers", {})
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
        isinstance(answers_any, dict)
        and not answers_any
        and isinstance(inputs_any, dict)
        and inputs_any
    ):
        state["answers"] = dict(inputs_any)
        changed = True

    if changed:
        state["updated_at"] = _iso_utc_now()
    return state


def _exception_envelope(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, SessionNotFoundError):
        return error_envelope(
            "NOT_FOUND",
            str(exc) or "not found",
            details=[{"path": "$.session_id", "reason": "not_found", "meta": {}}],
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
