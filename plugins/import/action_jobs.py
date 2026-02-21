"""Action job request extraction for import sessions.

This module derives PHASE 1 action-step job requests from the effective
WizardDefinition step ordering.

ASCII-only.
"""

from __future__ import annotations

from typing import Any


def extract_action_job_requests(
    *,
    wizard_definition: dict[str, Any],
    effective_step_order: list[str],
) -> list[dict[str, Any]] | None:
    """Return PHASE 1 action-step job_request objects or None.

    Selection rules:
    - phase == 1 (derived: only 'processing' is PHASE 2)
    - execution == "job"
    - step contains job_request (dict)

    Output: canonical JSON list (ordered by effective_step_order).
    """

    steps_any = wizard_definition.get("steps") if isinstance(wizard_definition, dict) else None
    if not isinstance(steps_any, list):
        return None

    by_id: dict[str, dict[str, Any]] = {}
    for s in steps_any:
        if not isinstance(s, dict):
            continue
        sid = s.get("step_id")
        if isinstance(sid, str) and sid:
            by_id[sid] = s

    out: list[dict[str, Any]] = []
    for step_id in effective_step_order:
        if step_id == "processing":
            continue
        s = by_id.get(step_id)
        if not isinstance(s, dict):
            continue
        execution = s.get("execution")
        if execution != "job":
            continue
        job_req = s.get("job_request")
        if not isinstance(job_req, dict):
            continue
        out.append(dict(job_req))

    if not out:
        return None
    return out
