"""Import wizard engine errors.

ASCII-only.
"""

from __future__ import annotations


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
