"""Web server control screen."""

from __future__ import annotations

from ..menu import Menu, MenuItem
from ..dialogs import Dialogs
from ..theme import Theme


class WebScreen:
    """Web server control screen."""
    
    def __init__(self, screen, theme: Theme, config: dict):
        """Initialize web screen.
        
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
        """Show web server menu.
        
        Returns:
            Selected action or "back"
        """
        items = [
            MenuItem(
                key="1",
                label="Start Web Server",
                desc="Start web interface on port 8080",
                action="start",
                visible=True
            ),
            MenuItem(
                key="2",
                label="Stop Web Server",
                desc="Stop running web server",
                action="stop",
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
            title="Web Server",
            items=items,
            footer="<Select>                                             <Back>"
        )
        
        if action == "start":
            self.dialogs.message(
                "Web Server",
                "Exit TUI and run:\n\n  audiomason web\n\nThen open: http://localhost:8080"
            )
        elif action == "stop":
            self.dialogs.message(
                "Web Server",
                "To stop web server, press Ctrl+C in the terminal\nwhere it's running."
            )
        
        return action
