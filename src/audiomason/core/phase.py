"""Phase contract enforcement.

Baseline contract:
- UI input collection may prompt.
- Processing must not prompt.

This guard is UI-agnostic (CLI, web, etc.).
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextvars import ContextVar
from enum import Enum


class Phase(str, Enum):
    UI_INPUT = "ui_input"
    PROCESSING = "processing"


_CURRENT_PHASE: ContextVar[Phase] = ContextVar("audiomason_phase", default=Phase.UI_INPUT)


class PhaseContractError(RuntimeError):
    """Raised when code violates the baseline phase contract."""


class PhaseGuard:
    """Small helper to set/check the current phase."""

    @staticmethod
    def current() -> Phase:
        return _CURRENT_PHASE.get()

    @staticmethod
    def require_ui_input(action: str) -> None:
        """Assert current phase is UI input.

        Args:
            action: Description of the operation being attempted.
        """
        if PhaseGuard.current() != Phase.UI_INPUT:
            raise PhaseContractError(f"UI-only operation attempted during processing: {action}")

    @staticmethod
    @contextlib.contextmanager
    def processing() -> Iterator[None]:
        token = _CURRENT_PHASE.set(Phase.PROCESSING)
        try:
            yield
        finally:
            _CURRENT_PHASE.reset(token)
