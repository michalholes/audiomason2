"""Action job request extraction for import sessions.

This module derives PHASE 1 action-step job requests from the effective
WizardDefinition step ordering.

ASCII-only.
"""

from __future__ import annotations

from typing import Any


def extract_action_job_requests(effective_model: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Return PHASE 1 action-step job_request objects or None.

    Source of truth is effective_model["steps"]. Selection rules:
    - step.phase == 1
    - step.execution == "job"
    - step.job_request is a dict

    Output: canonical JSON list ordered by effective_model["steps"].
    """

    steps_any = effective_model.get("steps") if isinstance(effective_model, dict) else None
    if not isinstance(steps_any, list):
        return None

    out: list[dict[str, Any]] = []
    for step in steps_any:
        if not isinstance(step, dict):
            continue
        if step.get("phase") != 1:
            continue
        if step.get("execution") != "job":
            continue
        job_req = step.get("job_request")
        if not isinstance(job_req, dict):
            continue
        out.append(dict(job_req))

    if not out:
        return None
    return out
