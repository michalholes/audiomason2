"""Import plugin entrypoint.

This plugin currently provides only the ImportWizardEngine.

ASCII-only.
"""

from __future__ import annotations

from audiomason.core.config import ConfigResolver

from .engine import ImportWizardEngine


class ImportPlugin:
    """Import plugin providing the ImportWizardEngine."""

    def __init__(self) -> None:
        self._resolver = ConfigResolver(cli_args={})
        self.engine = ImportWizardEngine(resolver=self._resolver)

    def get_engine(self) -> ImportWizardEngine:
        return self.engine
