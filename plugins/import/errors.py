"""Import wizard engine errors.

ASCII-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
    """Return a canonical ErrorEnvelope dict."""

    return ErrorEnvelope(code=code, message=message, details=details or []).to_dict()


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
