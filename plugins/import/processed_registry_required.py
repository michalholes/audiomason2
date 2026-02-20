"""Core-facing processed registry integration for the import plugin.

Subscribes to diagnostics events and updates the processed registry when
import-generated PROCESS jobs succeed.

This module intentionally avoids importing multiple external areas directly.

ASCII-only.
"""

from __future__ import annotations

import contextlib
from typing import Any

from . import core_facade, file_io_facade
from .processed_registry import apply_successful_job_requests
from .storage import read_json

_INSTALLED = False


def install_processed_registry_subscriber(*, resolver: Any) -> None:
    """Install the processed registry subscriber (idempotent)."""

    global _INSTALLED
    if _INSTALLED:
        return

    fs = file_io_facade.file_service_from_resolver(resolver)

    def _on_any(event: str, payload: dict[str, Any]) -> None:
        if event != "diag.job.end":
            return
        if not isinstance(payload, dict):
            return

        data_any = payload.get("data")
        if not isinstance(data_any, dict):
            return

        if data_any.get("status") != "succeeded":
            return

        job_id = data_any.get("job_id")
        job_type = data_any.get("job_type")
        if job_type != "process":
            return
        if not isinstance(job_id, str) or not job_id:
            return

        with contextlib.suppress(Exception):
            job = core_facade.get_job_service().get_job(job_id)
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

            root = file_io_facade.ROOT_MAP.get(str(root_str))
            if root is None:
                return

            job_requests_any = read_json(fs, root, rel_path)
            if not isinstance(job_requests_any, dict):
                return

            apply_successful_job_requests(fs, job_requests_any)

    core_facade.get_bus().subscribe_all(_on_any)
    _INSTALLED = True


# Backward-compatible name used by older code paths.
_install_processed_registry_subscriber = install_processed_registry_subscriber
