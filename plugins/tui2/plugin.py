"""tui2 plugin: Terminal UI for AudioMason2.

This plugin is plugin-only and does not modify core or other plugins.
"""

from __future__ import annotations

import argparse
from typing import Any


class TUI2Plugin:
    """Plugin implementing the ICLICommands contract."""

    def get_cli_commands(self) -> dict[str, Any]:
        return {"tui2": self.run_tui}

    def run_tui(self, argv: list[str]) -> str:
        parser = argparse.ArgumentParser(prog="audiomason tui2", add_help=True)
        parser.add_argument("--refresh-ms", type=int, default=500)
        parser.add_argument("--no-color", action="store_true")
        parser.parse_args(argv)

        # Minimal stub: real ncurses UI will be implemented in subsequent patches.
        print("tui2: stub (ncurses UI not implemented yet)")
        return "OK"
