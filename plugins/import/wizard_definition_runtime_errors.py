"""Structured runtime errors for authored wizard definition loading.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from .field_schema_validation import FieldSchemaValidationError

_ACTIVE_WIZARD_PATH = "wizards/import/definitions/wizard_definition.json"
_ACTIVE_WIZARD_HINT = (
    "Fix or replace wizards/import/definitions/wizard_definition.json, or remove it "
    "to regenerate the shipped default."
)


def invalid_authored_wizard_definition_error(
    exc: Exception,
    *,
    reason: str = "invalid_authored_wizard_definition",
) -> FieldSchemaValidationError:
    path = "$"
    meta: dict[str, Any] = {
        "artifact_path": _ACTIVE_WIZARD_PATH,
        "hint": _ACTIVE_WIZARD_HINT,
        "source_error_type": exc.__class__.__name__,
    }
    if isinstance(exc, FieldSchemaValidationError):
        path = str(exc.path) or "$"
        meta.update(dict(exc.meta))
        meta["source_reason"] = str(exc.reason) or "validation_error"
    return FieldSchemaValidationError(
        message=(
            "wizard_definition runtime artifact is invalid; "
            "fix or replace wizards/import/definitions/wizard_definition.json"
        ),
        path=path,
        reason=reason,
        meta=meta,
    )
