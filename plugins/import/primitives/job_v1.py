"""Baseline v1 job primitives for import DSL runtime.

ASCII-only.
"""

from __future__ import annotations

from typing import TypeGuard, cast

from ..fingerprints import sha256_hex


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_str_list(value: object) -> list[str]:
    if not _is_object_list(value):
        return []
    return [item for item in value if isinstance(item, str)]


def _object_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {},
        "required": [],
        "description": "",
    }


REGISTRY_ENTRIES: list[dict[str, object]] = [
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
    state: dict[str, object],
    inputs: dict[str, object],
) -> tuple[dict[str, object], str]:
    jobs = state.get("jobs")
    jobs_doc = jobs if _is_str_object_dict(jobs) else {}
    emitted = _as_str_list(jobs_doc.get("emitted"))
    job_id = _job_id(session_id=session_id, step_id=step_id, index=len(emitted) + 1)
    return {"job_id": job_id, "request": dict(inputs)}, job_id


def execute_submit(
    *, state: dict[str, object], inputs: dict[str, object]
) -> tuple[dict[str, object], str]:
    job_id = inputs.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("job.submit@1 requires job_id")
    jobs = state.get("jobs")
    jobs_doc = jobs if _is_str_object_dict(jobs) else {}
    emitted = _as_str_list(jobs_doc.get("emitted"))
    if job_id not in emitted:
        raise RuntimeError("job.submit@1 requires previously emitted job_id")
    return {"job_id": job_id}, job_id
