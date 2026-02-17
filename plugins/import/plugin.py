"""Import plugin entrypoint.

This plugin currently provides only the ImportWizardEngine.

ASCII-only.
"""

from __future__ import annotations

from audiomason.core.config import ConfigResolver

from .cli import import_cli_main
from .engine import ImportWizardEngine


class ImportPlugin:
    """Import plugin providing the ImportWizardEngine."""

    def __init__(self, resolver: ConfigResolver | None = None) -> None:
        # Fallback resolver is for tests only. Real hosts must provide a resolver.
        self._resolver = resolver or ConfigResolver(cli_args={})
        self.engine = ImportWizardEngine(resolver=self._resolver)

    def get_engine(self) -> ImportWizardEngine:
        return self.engine

    def get_cli_commands(self) -> dict[str, object]:
        """Return plugin-provided CLI command handlers.

        This plugin provides the top-level 'import' command.
        """
        return {"import": lambda argv: import_cli_main(argv, engine=self.engine)}
