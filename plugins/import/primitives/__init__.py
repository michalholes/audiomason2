"""Stable dispatch surface for import DSL baseline primitives.

ASCII-only.
"""

from __future__ import annotations

from typing import TypeGuard, cast

from . import (
    call_v1,
    control_v1,
    data_v1,
    fork_join_v1,
    io_v1,
    job_v1,
    loop_v1,
    parallel_v1,
    source_v1,
    subflow_v1,
    ui_v1,
)


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _as_str_list(value: object) -> list[str]:
    if not _is_object_list(value):
        return []
    return [item for item in value if isinstance(item, str)]


def _registry_sort_key(item: dict[str, object]) -> tuple[str, int]:
    version_any = item.get("version")
    version = version_any if isinstance(version_any, int) else 0
    return (str(item.get("primitive_id") or ""), version)


_REGISTRY_ENTRIES: list[dict[str, object]] = sorted(
    [
        *ui_v1.REGISTRY_ENTRIES,
        *call_v1.REGISTRY_ENTRIES,
        *control_v1.REGISTRY_ENTRIES,
        *data_v1.REGISTRY_ENTRIES,
        *io_v1.REGISTRY_ENTRIES,
        *job_v1.REGISTRY_ENTRIES,
        *parallel_v1.REGISTRY_ENTRIES,
        *fork_join_v1.REGISTRY_ENTRIES,
        *source_v1.REGISTRY_ENTRIES,
        *subflow_v1.REGISTRY_ENTRIES,
        *loop_v1.REGISTRY_ENTRIES,
    ],
    key=_registry_sort_key,
)


NON_INTERACTIVE_IDS: set[str] = {
    "ui.message",
    "call.invoke",
    "ctrl.if",
    "ctrl.switch",
    "ctrl.guard",
    "ctrl.stop",
    "data.set",
    "data.unset",
    "data.filter",
    "data.map",
    "data.group_by",
    "data.sort",
    "data.format",
    "source.build_catalog",
    "source.normalize_label",
    "source.keys",
    "source.resolve_selection",
    "io.list",
    "io.stat",
    "io.read_meta",
    "job.emit",
    "job.submit",
    "parallel.map",
    "parallel.fork_join",
    "flow.invoke",
    "flow.loop",
}


JOB_EMIT_ID = "job.emit"
JOB_SUBMIT_ID = "job.submit"
CTRL_STOP_ID = "ctrl.stop"


def baseline_registry_entries() -> list[dict[str, object]]:
    return [dict(item) for item in _REGISTRY_ENTRIES]


def is_prompt_primitive(primitive_id: str, primitive_version: int) -> bool:
    return ui_v1.is_prompt_primitive(primitive_id, primitive_version)


def is_non_interactive(primitive_id: str, primitive_version: int) -> bool:
    return primitive_version == 1 and primitive_id in NON_INTERACTIVE_IDS


def validate_submit_payload(
    primitive_id: str,
    primitive_version: int,
    payload: dict[str, object],
) -> dict[str, object]:
    return ui_v1.validate_submit_payload(primitive_id, primitive_version, payload)


def execute_non_prompt(
    *,
    session_id: str,
    step_id: str,
    primitive_id: str,
    primitive_version: int,
    inputs: dict[str, object],
    state: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    jobs: dict[str, object] = _as_str_object_dict(state.get("jobs"))
    if not jobs:
        jobs = {"emitted": list[str](), "submitted": list[str]()}
    emitted = _as_str_list(jobs.get("emitted"))
    submitted = _as_str_list(jobs.get("submitted"))

    if primitive_id == "ui.message":
        return ui_v1.execute_non_prompt(primitive_id, primitive_version, inputs), jobs
    if primitive_id == "call.invoke":
        return call_v1.execute(primitive_id, primitive_version, inputs, state), jobs
    if primitive_id.startswith("ctrl."):
        return control_v1.execute(primitive_id, primitive_version, inputs), jobs
    if primitive_id.startswith("data.") or primitive_id == "source.resolve_selection":
        return data_v1.execute(primitive_id, primitive_version, inputs, state), jobs
    if primitive_id in {"source.build_catalog", "source.normalize_label", "source.keys"}:
        return source_v1.execute(primitive_id, primitive_version, inputs, state), jobs
    if primitive_id.startswith("io."):
        return io_v1.execute(primitive_id, primitive_version, inputs), jobs
    if primitive_id == JOB_EMIT_ID:
        outputs, job_id = job_v1.execute_emit(
            session_id=session_id,
            step_id=step_id,
            state=state,
            inputs=inputs,
        )
        emitted.append(job_id)
        jobs["emitted"] = emitted
        jobs["submitted"] = submitted
        return outputs, jobs
    if primitive_id == JOB_SUBMIT_ID:
        outputs, job_id = job_v1.execute_submit(state=state, inputs=inputs)
        if job_id not in submitted:
            submitted.append(job_id)
        jobs["emitted"] = emitted
        jobs["submitted"] = submitted
        return outputs, jobs
    if primitive_id == "parallel.map":
        return parallel_v1.execute(primitive_id, primitive_version, inputs), jobs
    raise ValueError("unknown primitive")


__all__ = [
    "CTRL_STOP_ID",
    "JOB_EMIT_ID",
    "JOB_SUBMIT_ID",
    "baseline_registry_entries",
    "execute_non_prompt",
    "is_non_interactive",
    "is_prompt_primitive",
    "validate_submit_payload",
]
