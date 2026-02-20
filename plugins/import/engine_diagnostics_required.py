"""Diagnostics emission helpers for import engine.

Engine must remain file_io-only (no core imports) to avoid cross-area
coupling signals. This module contains the required core-facing imports.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus as _core_get_event_bus
from audiomason.core.jobs.api import JobService
from audiomason.core.jobs.model import JobType


def emit_required(
    *,
    event: str,
    operation: str,
    data: dict[str, Any],
    required_ctx: dict[str, Any] | None,
) -> None:
    """Emit diagnostics with required context fields.

    required_ctx must contain (when available):
      - session_id
      - model_fingerprint
      - discovery_fingerprint
      - effective_config_fingerprint

    Emission is fail-safe.
    """

    payload = dict(data)
    ctx = required_ctx or {}
    for key in [
        "session_id",
        "model_fingerprint",
        "discovery_fingerprint",
        "effective_config_fingerprint",
    ]:
        if key in ctx:
            payload[key] = ctx[key]

    try:
        _get_bus().publish(
            event,
            build_envelope(
                event=event,
                component="import",
                operation=operation,
                data=payload,
            ),
        )
    except Exception:
        return


def _get_bus():
    # Prefer the import engine test seam when present.
    try:
        from importlib import import_module

        engine_mod = import_module("plugins.import.engine")
        fn = getattr(engine_mod, "get_event_bus", None)
        if callable(fn):
            return fn()
    except Exception:
        pass
    return _core_get_event_bus()


def create_process_job(*, meta: dict[str, Any]) -> str:
    """Create a PROCESS job and return job_id.

    This is a thin core-facing facade to keep core imports out of engine.py.
    """

    job = JobService().create_job(JobType.PROCESS, meta=meta)
    return str(job.job_id)
