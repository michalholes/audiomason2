"""Import engine UI helper APIs.

This module contains thin helpers that are used by UI layers but do not perform
state transitions.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from .dsl.flowmodel_v3 import FLOWMODEL_KIND
from .dsl.interpreter_v3 import prompt_ui_from_resolved_inputs, resolve_inputs
from .engine_util import _exception_envelope
from .primitives import is_prompt_primitive


def get_step_definition_impl(*, engine: Any, session_id: str, step_id: str) -> dict[str, Any]:
    """Return the catalog step definition for step_id.

    This is a UI helper. It does not perform any state transitions.
    """
    try:
        effective_model = engine._load_effective_model(session_id)
        state = engine._load_state(session_id)
        steps_any = effective_model.get("steps")
        if not isinstance(steps_any, list):
            raise ValueError("effective model missing steps")
        current_step_id = str(
            (state.get("cursor") or {}).get("step_id") or state.get("current_step_id") or ""
        )
        for step in steps_any:
            if not isinstance(step, dict) or step.get("step_id") != step_id:
                continue
            out = dict(step)
            primitive_id = str(step.get("primitive_id") or "")
            primitive_version = int(step.get("primitive_version") or 0)
            is_v3 = str(effective_model.get("flowmodel_kind") or "") == FLOWMODEL_KIND
            if is_v3 and step_id == current_step_id:
                if is_prompt_primitive(primitive_id, primitive_version):
                    inputs = resolve_inputs(step, state)
                    ui = prompt_ui_from_resolved_inputs(inputs)
                    if ui:
                        out["ui"] = ui
                    else:
                        out.pop("ui", None)
                else:
                    out.pop("ui", None)
            return out
        raise ValueError("unknown step_id")
    except Exception as e:
        return _exception_envelope(e)
