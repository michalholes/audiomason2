"""Models used by the core orchestration layer.

These models are intentionally UI-agnostic so they can be used by CLI and the
future web interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from audiomason.core.context import ProcessingContext


@dataclass(frozen=True)
class ProcessRequest:
    contexts: list[ProcessingContext]
    pipeline_path: Path
    plugin_loader: Any


@dataclass(frozen=True)
class WizardRequest:
    wizard_id: str
    # Backwards-compatible single-target field.
    wizard_path: Path
    plugin_loader: Any
    payload: dict[str, Any]
    # Optional multi-target support (batch mode). When provided, orchestration
    # executes the wizard once per target, using ProcessingContext.source.
    wizard_paths: list[Path] | None = None
    verbosity: int = 1
