"""Action job request extraction for import sessions.

This module derives PHASE 1 action-step job requests from the effective
WizardDefinition step ordering.

ASCII-only.
"""

from __future__ import annotations

from typing import TypeGuard


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def extract_action_job_requests(
    effective_model: dict[str, object],
) -> list[dict[str, object]] | None:
    """Return PHASE 1 action-step job_request objects or None.

    Source of truth is effective_model["steps"]. Selection rules:
    - step.phase == 1
    - step.execution == "job"
    - step.job_request is a dict

    Output: canonical JSON list ordered by effective_model["steps"].
    """

    steps_any = effective_model.get("steps")
    if not _is_object_list(steps_any):
        return None

    out: list[dict[str, object]] = []
    for step in steps_any:
        if not _is_str_object_dict(step):
            continue
        if step.get("phase") != 1:
            continue
        if step.get("execution") != "job":
            continue
        job_req = step.get("job_request")
        if not _is_str_object_dict(job_req):
            continue
        out.append(dict(job_req))

    if not out:
        return None
    return out
