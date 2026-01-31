"""TUI theme system - colors and configuration."""

from __future__ import annotations

import curses
from typing import Any


# Raspi-config color scheme
RASPI_CONFIG_THEME = {
    "title_bg": curses.COLOR_RED,
    "title_fg": curses.COLOR_WHITE,
    "menu_bg": curses.COLOR_WHITE,
    "menu_fg": curses.COLOR_BLACK,
    "selected_bg": curses.COLOR_WHITE,
    "selected_fg": curses.COLOR_BLACK,
    "success_fg": curses.COLOR_GREEN,
    "error_fg": curses.COLOR_RED,
}

# AudioMason color scheme (blue theme)
AUDIOMASON_THEME = {
    "title_bg": curses.COLOR_BLUE,
    "title_fg": curses.COLOR_WHITE,
    "menu_bg": curses.COLOR_BLACK,
    "menu_fg": curses.COLOR_WHITE,
    "selected_bg": curses.COLOR_WHITE,
    "selected_fg": curses.COLOR_BLACK,
    "success_fg": curses.COLOR_GREEN,
    "error_fg": curses.COLOR_RED,
}

# Color name to curses constant mapping
COLOR_NAMES = {
    "black": curses.COLOR_BLACK,
    "red": curses.COLOR_RED,
    "green": curses.COLOR_GREEN,
    "yellow": curses.COLOR_YELLOW,
    "blue": curses.COLOR_BLUE,
    "magenta": curses.COLOR_MAGENTA,
    "cyan": curses.COLOR_CYAN,
    "white": curses.COLOR_WHITE,
    "lightgray": curses.COLOR_WHITE,  # Alias
}


class Theme:
    """TUI theme manager."""
    
    # Color pair IDs
    PAIR_TITLE = 1
    PAIR_MENU = 2
    PAIR_SELECTED = 3
    PAIR_SUCCESS = 4
    PAIR_ERROR = 5
    
    def __init__(self, config: dict[str, Any] | None = None):
        """Initialize theme.
        
        Args:
            config: Theme configuration
        """
        self.config = config or {}
        self._colors = self._load_colors()
    
    def _load_colors(self) -> dict[str, int]:
        """Load color scheme based on config.
        
        Returns:
            Color scheme dict
        """
        theme_name = self.config.get("theme", "raspi-config")
        
        if theme_name == "raspi-config":
            return RASPI_CONFIG_THEME.copy()
        elif theme_name == "audiomason":
            return AUDIOMASON_THEME.copy()
        elif theme_name == "custom":
            return self._load_custom_colors()
        else:
            return RASPI_CONFIG_THEME.copy()
    
    def _load_custom_colors(self) -> dict[str, int]:
        """Load custom color scheme from config.
        
        Returns:
            Custom color scheme
        """
        custom = self.config.get("custom_theme", {})
        colors = {}
        
        for key, default in RASPI_CONFIG_THEME.items():
            color_name = custom.get(key, "").lower()
            colors[key] = COLOR_NAMES.get(color_name, default)
        
        return colors
    
    def init_colors(self) -> None:
        """Initialize curses color pairs."""
        # Title (red background, white text for raspi-config)
        curses.init_pair(
            self.PAIR_TITLE,
            self._colors["title_fg"],
            self._colors["title_bg"]
        )
        
        # Menu (gray background for raspi-config)
        curses.init_pair(
            self.PAIR_MENU,
            self._colors["menu_fg"],
            self._colors["menu_bg"]
        )
        
        # Selected item (white background, black text)
        curses.init_pair(
            self.PAIR_SELECTED,
            self._colors["selected_fg"],
            self._colors["selected_bg"]
        )
        
        # Success messages (green)
        curses.init_pair(
            self.PAIR_SUCCESS,
            self._colors["success_fg"],
            curses.COLOR_BLACK
        )
        
        # Error messages (red)
        curses.init_pair(
            self.PAIR_ERROR,
            self._colors["error_fg"],
            curses.COLOR_BLACK
        )
    
    def get_color_pair(self, pair_id: int) -> int:
        """Get curses color pair.
        
        Args:
            pair_id: Color pair ID
            
        Returns:
            Curses color pair
        """
        return curses.color_pair(pair_id)
