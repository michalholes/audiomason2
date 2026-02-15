"""Import plugin (ICLICommands).

Provides the `audiomason import` CLI command.

Issue 600:
- Import workflow ownership belongs to plugins/import.
- plugins/cli is only the host/dispatcher.
"""

from __future__ import annotations

from typing import Any

from .cli_entry import run_import_cli


class ImportPlugin:
    """Plugin implementing ICLICommands for `audiomason import`."""

    def get_cli_commands(self) -> dict[str, Any]:
        return {"import": self._handle_import}

    async def _handle_import(self, argv: list[str]) -> int:
        return await run_import_cli(argv)
