"""Main menu screen."""

from __future__ import annotations

from ..menu import Menu, MenuItem
from ..dialogs import Dialogs
from ..theme import Theme


class MainScreen:
    """Main menu screen."""
    
    def __init__(self, screen, theme: Theme, config: dict):
        """Initialize main screen.
        
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
        """Show main menu.
        
        Returns:
            Selected action
        """
        # Load menu items from config
        items = []
        menu_config = self.config.get("main_menu", [])
        
        for item_cfg in menu_config:
            items.append(MenuItem(
                key=item_cfg["key"],
                label=item_cfg["label"],
                desc=item_cfg["desc"],
                action=item_cfg["action"],
                visible=item_cfg.get("visible", True)
            ))
        
        # Show menu
        return self.menu.show(
            title="AudioMason v2 - Main Menu",
            items=items,
            footer="<Select>                                             <Finish>"
        )
