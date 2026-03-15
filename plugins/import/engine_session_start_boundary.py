"""User-facing import session start boundary.

This module centralizes explicit start intent handling for CLI and Web
surfaces while keeping raw engine.create_session semantics unchanged.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from plugins.file_io.service.types import RootName

from .engine_session_create import (
    create_new_session_from_context,
    emit_session_start_diagnostics,
    resolve_session_start_conflict,
    resolve_session_start_context,
    resume_session_from_context,
)
from .errors import error_envelope

ALLOWED_USER_START_INTENTS = {"resume", "new"}


def build_start_conflict_envelope(
    *,
    session_id: str,
    root: str,
    relative_path: str,
    mode: str,
) -> dict[str, Any]:
    return error_envelope(
        "SESSION_START_CONFLICT",
        "existing session requires explicit start intent",
        details=[
            {
                "path": "$.intent",
                "reason": "session_start_conflict",
                "meta": {
                    "allowed_intents": ["resume", "new"],
                    "session_id": session_id,
                    "root": root,
                    "relative_path": relative_path,
                    "mode": mode,
                },
            }
        ],
    )


def _validate_intent(intent: str | None) -> str | None:
    if intent is None:
        return None
    normalized = str(intent).strip().lower()
    if not normalized:
        return None
    if normalized not in ALLOWED_USER_START_INTENTS:
        raise ValueError("intent must be one of: new, resume")
    return normalized


def start_user_facing_session(
    *,
    engine: Any,
    root: str,
    relative_path: str,
    mode: str,
    intent: str | None,
    flow_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_intent = _validate_intent(intent)
    ctx = resolve_session_start_context(
        engine=engine,
        root=root,
        relative_path=relative_path,
        mode=mode,
        flow_overrides=flow_overrides,
    )
    if isinstance(ctx, dict):
        return ctx

    conflict = resolve_session_start_conflict(
        engine=engine,
        root=root,
        relative_path=relative_path,
        mode=mode,
        flow_overrides=flow_overrides,
    )
    if conflict is None:
        emit_session_start_diagnostics(ctx=ctx)
        return create_new_session_from_context(engine=engine, ctx=ctx)

    if normalized_intent is None:
        return build_start_conflict_envelope(
            session_id=conflict.session_id,
            root=conflict.root,
            relative_path=conflict.relative_path,
            mode=conflict.mode,
        )

    emit_session_start_diagnostics(ctx=ctx)
    if normalized_intent == "resume":
        return resume_session_from_context(engine=engine, ctx=ctx)

    session_dir = f"import/sessions/{ctx.session_id}"
    engine._fs.delete_path(RootName.WIZARDS, session_dir, missing_ok=False)
    return create_new_session_from_context(engine=engine, ctx=ctx)
