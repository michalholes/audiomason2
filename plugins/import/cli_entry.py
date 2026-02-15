"""CLI entry point for the import plugin.

Public API:
    async def run_import_cli(argv: list[str]) -> int

This module is UI glue:
- Creates the console UI implementation
- Delegates all state transitions to cli_flow.flow
"""

from __future__ import annotations

from .cli_flow.console_ui import ConsoleUI
from .cli_flow.flow import run_import_cli_flow


async def run_import_cli(argv: list[str]) -> int:
    """Run the import CLI command.

    Args:
        argv: argv after the command name, as provided by the CLI host.

    Returns:
        Process exit code.
    """

    ui = ConsoleUI()
    return await run_import_cli_flow(argv, ui)
