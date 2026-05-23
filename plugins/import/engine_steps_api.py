"""Import engine UI helper APIs.

This module contains thin helpers that are used by UI layers but do not perform
state transitions.

ASCII-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeGuard, cast

from .dsl.flowmodel_v3 import FLOWMODEL_KIND
from .dsl.interpreter_v3 import prompt_ui_from_resolved_inputs, resolve_inputs
from .engine_util import exception_envelope
from .primitives import is_prompt_primitive
from .prompt_select_ui_projection import build_prompt_select_ui_items

if TYPE_CHECKING:
    from .engine import ImportWizardEngine


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def get_step_definition_impl(
    *, engine: ImportWizardEngine, session_id: str, step_id: str
) -> dict[str, object]:
    """Return the catalog step definition for step_id.

    This is a UI helper. It does not perform any state transitions.
    """
    try:
        effective_model = engine.load_effective_model(session_id)
        state = engine.load_state(session_id)
        steps_any = effective_model.get("steps")
        if not _is_object_list(steps_any):
            raise ValueError("effective model missing steps")
        steps = steps_any
        cursor = state.get("cursor")
        cursor_dict = cursor if _is_str_object_dict(cursor) else {}
        current_step_id = str(cursor_dict.get("step_id") or state.get("current_step_id") or "")
        for step in steps:
            if not _is_str_object_dict(step) or step.get("step_id") != step_id:
                continue
            out = dict(step)
            primitive_id = str(step.get("primitive_id") or "")
            primitive_version_any = step.get("primitive_version")
            primitive_version = (
                primitive_version_any if isinstance(primitive_version_any, int) else 0
            )
            is_v3 = str(effective_model.get("flowmodel_kind") or "") == FLOWMODEL_KIND
            if is_v3 and step_id == current_step_id:
                if is_prompt_primitive(primitive_id, primitive_version):
                    inputs = resolve_inputs(step, state)
                    ui = prompt_ui_from_resolved_inputs(inputs)
                    if primitive_id == "ui.prompt_select":
                        items = build_prompt_select_ui_items(step_id=step_id, state=state)
                        if items:
                            ui["items"] = items
                    if ui:
                        out["ui"] = ui
                    else:
                        if "ui" in out:
                            del out["ui"]
                else:
                    if "ui" in out:
                        del out["ui"]
            return out
        raise ValueError("unknown step_id")
    except Exception as e:
        return exception_envelope(e)
