"""Shared completion authority for import PROCESS contract jobs.

ASCII-only.
"""

from __future__ import annotations

from typing import Protocol, TypeGuard, cast

from plugins.file_io.service import FileService, RootName

from .detached_runtime import load_canonical_job_requests
from .finalize_reports import write_success_finalize_artifacts
from .ignore_registry import apply_successful_job_requests as apply_ignore_registry
from .phase2_job_runner import run_phase2_job_requests
from .processed_registry import apply_successful_job_requests
from .storage import read_json


class _SupportsFileService(Protocol):
    def get_file_service(self) -> FileService: ...


class _PluginLoader(Protocol):
    def get_plugin(self, name: str) -> object: ...


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _state_path(*, session_id: str) -> str:
    return f"import/sessions/{session_id}/state.json"


def successful_process_completion_already_applied(
    *,
    fs: FileService,
    job_id: str,
    job_requests: dict[str, object],
) -> bool:
    """Return True when shared success completion already owns this job."""

    session_id = str(job_requests.get("session_id") or "")
    if not session_id:
        return False

    state_path = _state_path(session_id=session_id)
    if not fs.exists(RootName.WIZARDS, state_path):
        return False

    state_any = read_json(fs, RootName.WIZARDS, state_path)
    if not _is_str_object_dict(state_any):
        return False

    computed = _as_str_object_dict(state_any.get("computed"))
    finalize_any = computed.get("finalize")
    if not _is_str_object_dict(finalize_any):
        return False

    report_path = finalize_any.get("report_path")

    return (
        finalize_any.get("job_id") == job_id
        and finalize_any.get("status") == "succeeded"
        and isinstance(report_path, str)
        and bool(report_path)
    )


def apply_successful_process_completion(
    *,
    fs: FileService,
    job_id: str,
    job_requests: dict[str, object],
) -> dict[str, object] | None:
    """Persist finalize artifacts and success-only registries."""

    if successful_process_completion_already_applied(
        fs=fs,
        job_id=job_id,
        job_requests=job_requests,
    ):
        return None

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
    engine: _SupportsFileService,
    job_id: str,
    job_meta: dict[str, object],
    plugin_loader: object,
) -> dict[str, object]:
    """Execute PHASE 2 and the shared success completion path."""

    await run_phase2_job_requests(
        engine=engine,
        job_id=job_id,
        job_meta=dict(job_meta),
        plugin_loader=cast(_PluginLoader, plugin_loader),
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
    "successful_process_completion_already_applied",
]
