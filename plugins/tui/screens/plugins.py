"""Plugins management screen."""

from __future__ import annotations

from pathlib import Path

from ..menu import Menu, MenuItem
from ..dialogs import Dialogs
from ..theme import Theme


class PluginsScreen:
    """Plugins management screen."""
    
    def __init__(self, screen, theme: Theme, config: dict):
        """Initialize plugins screen.
        
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
        """Show plugins menu.
        
        Returns:
            Selected action or "back"
        """
        # Find plugins directory
        plugins_dir = Path(__file__).parent.parent.parent.parent
        
        # Scan for plugins
        plugin_dirs = [d for d in plugins_dir.iterdir() if d.is_dir() and (d / "plugin.yaml").exists()]
        
        items = []
        for i, plugin_dir in enumerate(sorted(plugin_dirs)):
            items.append(MenuItem(
                key=str(i + 1),
                label=plugin_dir.name,
                desc="Installed",
                action=f"plugin:{plugin_dir.name}",
                visible=True
            ))
        
        items.append(MenuItem(
            key="0",
            label="Back",
            desc="Return to main menu",
            action="back",
            visible=True
        ))
        
        action = self.menu.show(
            title="Plugin Management",
            items=items,
            footer="<Select>                                             <Back>"
        )
        
        if action.startswith("plugin:"):
            plugin_name = action[7:]
            self.dialogs.message(
                "Plugin Info",
                f"Plugin: {plugin_name}\n\nFeature coming soon:\n- Enable/Disable\n- Configure\n- Delete"
            )
        
        return action
