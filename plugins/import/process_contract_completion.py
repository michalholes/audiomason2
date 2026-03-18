"""Shared completion authority for import PROCESS contract jobs.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from .detached_runtime import load_canonical_job_requests
from .finalize_reports import write_success_finalize_artifacts
from .ignore_registry import apply_successful_job_requests as apply_ignore_registry
from .phase2_job_runner import run_phase2_job_requests
from .processed_registry import apply_successful_job_requests


def apply_successful_process_completion(
    *,
    fs: Any,
    job_id: str,
    job_requests: dict[str, Any],
) -> dict[str, Any] | None:
    """Persist finalize artifacts and success-only registries."""

    report = write_success_finalize_artifacts(
        fs=fs,
        job_id=job_id,
        job_requests=job_requests,
    )
    apply_successful_job_requests(fs, job_requests)
    apply_ignore_registry(fs, job_requests)
    return report


async def run_process_contract_completion(
    *,
    engine: Any,
    job_id: str,
    job_meta: dict[str, Any],
    plugin_loader: Any,
) -> dict[str, Any]:
    """Execute PHASE 2 and the shared success completion path."""

    await run_phase2_job_requests(
        engine=engine,
        job_id=job_id,
        job_meta=dict(job_meta),
        plugin_loader=plugin_loader,
    )

    fs = engine.get_file_service()
    job_requests = load_canonical_job_requests(fs=fs, job_meta=job_meta)
    apply_successful_process_completion(
        fs=fs,
        job_id=job_id,
        job_requests=job_requests,
    )
    return job_requests


__all__ = [
    "apply_successful_process_completion",
    "run_process_contract_completion",
]
