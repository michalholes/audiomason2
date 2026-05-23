"""Import wizard engine errors.

ASCII-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeGuard, cast


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _ascii_message(message: str) -> str:
    try:
        return message.encode("ascii").decode("ascii")
    except UnicodeEncodeError:
        return message.encode("ascii", "replace").decode("ascii")


def ascii_message(message: str) -> str:
    """Return message sanitized to ASCII-only (spec 10.4.1)."""

    return _ascii_message(str(message))


def _detail(
    path: str,
    reason: str,
    meta: dict[str, object] | None = None,
) -> dict[str, object]:
    if meta is None:
        meta = {}
    return {"path": path, "reason": reason, "meta": dict(meta)}


@dataclass(frozen=True)
class ErrorEnvelope:
    code: str
    message: str
    details: list[dict[str, object]]

    def to_dict(self) -> dict[str, object]:
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
    details: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Return a canonical ErrorEnvelope dict.

    Spec shape (10.4.1):
      {"error": {"code": ..., "message": ..., "details": [{"path","reason","meta"}, ...]}}
    """

    safe_details: list[dict[str, object]] = []
    for d in details or []:
        if not _is_str_object_dict(d):
            continue
        path = d.get("path")
        reason = d.get("reason")
        meta = d.get("meta")
        if not isinstance(path, str) or not path:
            path = "$"
        if not isinstance(reason, str) or not reason:
            reason = "invalid_detail"
        meta_obj = dict(meta) if _is_str_object_dict(meta) else {}
        safe_details.append(_detail(path, reason, meta_obj))

    return ErrorEnvelope(
        code=code, message=_ascii_message(str(message)), details=safe_details
    ).to_dict()


def validation_error(
    *,
    message: str,
    path: str,
    reason: str,
    meta: dict[str, object] | None = None,
) -> dict[str, object]:
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
    meta: dict[str, object] | None = None,
) -> dict[str, object]:
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
