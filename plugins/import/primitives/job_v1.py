"""Baseline v1 job primitives for import DSL runtime.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from ..fingerprints import sha256_hex


def _object_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {},
        "required": [],
        "description": "",
    }


REGISTRY_ENTRIES: list[dict[str, Any]] = [
    {
        "primitive_id": "job.emit",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": [],
    },
    {
        "primitive_id": "job.submit",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": ["INVARIANT_VIOLATION"],
    },
]


def _job_id(*, session_id: str, step_id: str, index: int) -> str:
    src = f"{session_id}|{step_id}|{index}"
    return "job:" + sha256_hex(src.encode("utf-8"))[:16]


def execute_emit(
    *,
    session_id: str,
    step_id: str,
    state: dict[str, Any],
    inputs: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    jobs_any = state.get("jobs")
    jobs = jobs_any if isinstance(jobs_any, dict) else {}
    emitted_any = jobs.get("emitted")
    emitted = list(emitted_any) if isinstance(emitted_any, list) else []
    job_id = _job_id(session_id=session_id, step_id=step_id, index=len(emitted) + 1)
    return {"job_id": job_id, "request": dict(inputs)}, job_id


def execute_submit(*, state: dict[str, Any], inputs: dict[str, Any]) -> tuple[dict[str, Any], str]:
    job_id = inputs.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("job.submit@1 requires job_id")
    jobs_any = state.get("jobs")
    jobs = jobs_any if isinstance(jobs_any, dict) else {}
    emitted_any = jobs.get("emitted")
    emitted = list(emitted_any) if isinstance(emitted_any, list) else []
    if job_id not in emitted:
        raise RuntimeError("job.submit@1 requires previously emitted job_id")
    return {"job_id": job_id}, job_id
