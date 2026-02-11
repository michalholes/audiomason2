"""TUI plugin - ncurses Terminal UI for AudioMason2.

Provides the `tui` CLI command via the ICLICommands interface.
This UI layer does not implement filesystem logic.
"""

from __future__ import annotations

import curses
from typing import Any

from audiomason.core.logging import get_logger

from .menu_engine import MenuEngine, MenuItem

log = get_logger(__name__)


class TUIPlugin:
    """TUI plugin implementing ICLICommands."""

    def __init__(self) -> None:
        self._engine: MenuEngine | None = None

    def get_cli_commands(self) -> dict[str, Any]:
        return {"tui": self._run_tui_command}

    def _run_tui_command(self, argv: list[str]) -> str:
        _ = argv
        try:
            curses.wrapper(self._run_curses)
            return "OK"
        except Exception as e:
            log.error(f"TUI error: {e}")
            return f"ERROR: {e}"

    def _run_curses(self, stdscr: Any) -> None:
        self._engine = MenuEngine(stdscr)
        self._engine.set_menu("Main Menu", self._build_main_menu())
        self._engine.run()

    def _build_main_menu(self) -> list[MenuItem]:
        return [
            MenuItem(id="plugins", label="1. Plugins", action=lambda: "Not implemented"),
            MenuItem(id="wizards", label="2. Wizards", action=lambda: "Not implemented"),
            MenuItem(id="jobs", label="3. Jobs", action=lambda: "Not implemented"),
            MenuItem(id="exit", label="4. Exit", action=self._action_exit),
        ]

    def _action_exit(self) -> str | None:
        if self._engine is not None:
            self._engine.running = False
        return None
