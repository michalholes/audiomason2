"""Phase contract enforcement.

Baseline contract:
- UI input collection may prompt.
- Processing must not prompt.

This guard is UI-agnostic (CLI, web, etc.).
"""

from __future__ import annotations

import builtins
import contextlib
from collections.abc import Callable, Iterator
from contextvars import ContextVar
from enum import Enum


class Phase(str, Enum):
    UI_INPUT = "ui_input"
    PROCESSING = "processing"


_CURRENT_PHASE: ContextVar[Phase] = ContextVar("audiomason_phase", default=Phase.UI_INPUT)

_INPUT_HOOK_DEPTH: ContextVar[int] = ContextVar("audiomason_phase_input_hook_depth", default=0)
_ORIGINAL_INPUT: ContextVar[Callable[..., str] | None] = ContextVar(
    "audiomason_phase_original_input", default=None
)


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
        depth = _INPUT_HOOK_DEPTH.get()

        if depth == 0:
            _ORIGINAL_INPUT.set(builtins.input)

            def _blocked_input(prompt: object = "") -> str:
                raise PhaseContractError(f"prompt attempted during processing: {prompt}")

            builtins.input = _blocked_input

        _INPUT_HOOK_DEPTH.set(depth + 1)
        try:
            yield
        finally:
            depth = _INPUT_HOOK_DEPTH.get() - 1
            _INPUT_HOOK_DEPTH.set(depth)

            if depth == 0:
                original = _ORIGINAL_INPUT.get()
                if original is not None:
                    builtins.input = original
                _ORIGINAL_INPUT.set(None)
            _CURRENT_PHASE.reset(token)
