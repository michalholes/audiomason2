"""Daemon mode control screen."""

from __future__ import annotations

from ..menu import Menu, MenuItem
from ..dialogs import Dialogs
from ..theme import Theme


class DaemonScreen:
    """Daemon mode control screen."""
    
    def __init__(self, screen, theme: Theme, config: dict):
        """Initialize daemon screen.
        
        Args:
            screen: Curses screen
            theme: Theme manager
            config: TUI configuration
        """
        self.screen = screen
        self.theme = theme
        self.config = config
        self.menu = Menu(screen, theme)
        self.dialogs = Dialogs(screen, theme)
    
    def show(self) -> str:
        """Show daemon menu.
        
        Returns:
            Selected action or "back"
        """
        items = [
            MenuItem(
                key="1",
                label="Start Daemon",
                desc="Start background folder watcher",
                action="start",
                visible=True
            ),
            MenuItem(
                key="2",
                label="Stop Daemon",
                desc="Stop background watcher",
                action="stop",
                visible=True
            ),
            MenuItem(
                key="3",
                label="Configure",
                desc="Edit daemon settings",
                action="config",
                visible=True
            ),
            MenuItem(
                key="0",
                label="Back",
                desc="Return to main menu",
                action="back",
                visible=True
            ),
        ]
        
        action = self.menu.show(
            title="Daemon Mode",
            items=items,
            footer="<Select>                                             <Back>"
        )
        
        if action == "start":
            self.dialogs.message(
                "Daemon Mode",
                "Exit TUI and run:\n\n  audiomason daemon\n\nIt will run in the foreground.\nPress Ctrl+C to stop."
            )
        elif action == "stop":
            self.dialogs.message(
                "Daemon Mode",
                "To stop daemon, press Ctrl+C in the terminal\nwhere it's running."
            )
        elif action == "config":
            # Return to config screen
            return "back"
        
        return action
