"""Import engine UI helper APIs.

This module contains thin helpers that are used by UI layers but do not perform
state transitions.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from .engine_util import _exception_envelope


def get_step_definition_impl(*, engine: Any, session_id: str, step_id: str) -> dict[str, Any]:
    """Return the catalog step definition for step_id.

    This is a UI helper. It does not perform any state transitions.
    """
    try:
        effective_model = engine._load_effective_model(session_id)
        steps_any = effective_model.get("steps")
        if not isinstance(steps_any, list):
            raise ValueError("effective model missing steps")
        for step in steps_any:
            if isinstance(step, dict) and step.get("step_id") == step_id:
                return dict(step)
        raise ValueError("unknown step_id")
    except Exception as e:
        return _exception_envelope(e)
