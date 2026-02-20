"""Core-facing processed registry integration for the import plugin.

Subscribes to diagnostics events and updates the processed registry when
import-generated PROCESS jobs succeed.

This module contains the required core imports to avoid coupling signals
inside engine.py.

ASCII-only.
"""

from __future__ import annotations

import contextlib
from typing import Any

from audiomason.core.events import get_event_bus as _core_get_event_bus
from audiomason.core.jobs.api import JobService

from plugins.file_io.service import FileService, RootName

from .processed_registry import apply_successful_job_requests
from .storage import read_json

_INSTALLED = False


def install_processed_registry_subscriber(*, resolver: Any) -> None:
    """Install the processed registry subscriber (idempotent)."""
    global _INSTALLED
    if _INSTALLED:
        return

    fs = FileService.from_resolver(resolver)

    def _on_any(event: str, payload: dict[str, Any]) -> None:
        if event != "diag.job.end":
            return
        if not isinstance(payload, dict):
            return

        data_any = payload.get("data")
        if not isinstance(data_any, dict):
            return

        status = data_any.get("status")
        if status != "succeeded":
            return

        job_id = data_any.get("job_id")
        job_type = data_any.get("job_type")
        if job_type != "process":
            return
        if not isinstance(job_id, str) or not job_id:
            return

        with contextlib.suppress(Exception):
            job = JobService().get_job(job_id)
            meta = dict(job.meta or {})
            if meta.get("source") != "import":
                return

            jr_path = meta.get("job_requests_path")
            if not isinstance(jr_path, str) or ":" not in jr_path:
                return

            root_str, rel_path = jr_path.split(":", 1)
            root_str = root_str.strip()
            rel_path = rel_path.strip().lstrip("/")
            if not root_str or not rel_path:
                return

            root = _root_from_str(root_str)
            if root is None:
                return

            job_requests_any = read_json(fs, root, rel_path)
            if not isinstance(job_requests_any, dict):
                return

            apply_successful_job_requests(fs, job_requests_any)

    _get_bus().subscribe_all(_on_any)
    _INSTALLED = True


_ROOT_MAP = {rn.value: rn for rn in RootName}


def _root_from_str(value: str):
    return _ROOT_MAP.get(str(value))


def _get_bus():
    # Prefer import plugin test seam.
    try:
        from importlib import import_module

        mod = import_module("plugins.import.processed_registry_required")
        fn = getattr(mod, "get_event_bus", None)
        if callable(fn):
            return fn()
    except Exception:
        pass
    return _core_get_event_bus()


# Test seam: unit tests may monkeypatch plugins.import.processed_registry_required.get_event_bus.
get_event_bus: Any = None
