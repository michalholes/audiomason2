"""Import wizard engine errors.

ASCII-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _ascii_message(message: str) -> str:
    try:
        return message.encode("ascii").decode("ascii")
    except UnicodeEncodeError:
        return message.encode("ascii", "replace").decode("ascii")


def _detail(
    path: str,
    reason: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if meta is None:
        meta = {}
    return {"path": path, "reason": reason, "meta": dict(meta)}


@dataclass(frozen=True)
class ErrorEnvelope:
    code: str
    message: str
    details: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": list(self.details),
            }
        }


def error_envelope(
    code: str,
    message: str,
    *,
    details: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a canonical ErrorEnvelope dict.

    Spec shape (10.4.1):
      {"error": {"code": ..., "message": ..., "details": [{"path","reason","meta"}, ...]}}
    """

    safe_details: list[dict[str, Any]] = []
    for d in details or []:
        if not isinstance(d, dict):
            continue
        path = d.get("path")
        reason = d.get("reason")
        meta = d.get("meta")
        if not isinstance(path, str) or not path:
            path = "$"
        if not isinstance(reason, str) or not reason:
            reason = "invalid_detail"
        if not isinstance(meta, dict):
            meta = {}
        safe_details.append(_detail(path, reason, meta))

    return ErrorEnvelope(
        code=code, message=_ascii_message(str(message)), details=safe_details
    ).to_dict()


def validation_error(
    *,
    message: str,
    path: str,
    reason: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return error_envelope(
        "VALIDATION_ERROR",
        message,
        details=[_detail(path, reason, meta)],
    )


def invariant_violation(
    *,
    message: str,
    path: str,
    reason: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return error_envelope(
        "INVARIANT_VIOLATION",
        message,
        details=[_detail(path, reason, meta)],
    )


class ImportWizardError(RuntimeError):
    pass


class ModelLoadError(ImportWizardError):
    pass


class ModelValidationError(ImportWizardError):
    pass


class SessionNotFoundError(ImportWizardError):
    pass


class StepSubmissionError(ImportWizardError):
    pass


class FinalizeError(ImportWizardError):
    pass
