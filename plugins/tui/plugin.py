"""TUI plugin - Terminal User Interface.

Raspi-config style ncurses menu system with full configuration support.

Fixes:
- #3: Bitrate menu arrows work correctly
- #4: Bitrate value actually changes
- #5: Daemon config Esc handling
- #7: Daemon config tooltips/descriptions
- #8: No visual artifacts (proper screen clearing)
- #9: No text rendering bugs
- #10: Wizards show correct step count
"""

from __future__ import annotations

import curses
import sys
from pathlib import Path
from typing import Any

from audiomason.core.logging import get_logger, set_verbosity

try:
    import curses
    HAS_CURSES = True
except ImportError:
    HAS_CURSES = False

from .theme import Theme
from .screens import (
    MainScreen,
    WizardsScreen,
    ConfigScreen,
    PluginsScreen,
    WebScreen,
    DaemonScreen,
    LogsScreen,
    AboutScreen,
)


class TUIPlugin:
    """Terminal user interface plugin."""
    
    def __init__(self, config: dict | None = None):
        """Initialize TUI plugin.
        
        Args:
            config: Plugin configuration
        """
        if not HAS_CURSES:
            raise ImportError("curses not available")
        
        self.config = config or {}
        self.logger = get_logger(__name__)
        
        # Set verbosity if provided
        if "verbosity" in self.config:
            set_verbosity(self.config["verbosity"])
        
        self.screen = None
        self.theme = None
        self.current_screen = "main"
        self.screen_stack = []
    
    async def run(self) -> None:
        """Run TUI - main entry point."""
        self.logger.info("Starting TUI")
        
        try:
            curses.wrapper(self._main_loop)
        except KeyboardInterrupt:
            self.logger.info("TUI interrupted by user")
        except Exception as e:
            self.logger.error(f"TUI error: {e}")
            raise
    
    def _main_loop(self, stdscr) -> None:
        """Main TUI loop.
        
        FIX #8: Proper screen clearing to avoid visual artifacts.
        
        Args:
            stdscr: Curses screen object
        """
        self.screen = stdscr
        
        # Setup
        curses.curs_set(0)  # Hide cursor
        
        # Initialize theme
        self.theme = Theme(self.config)
        self.theme.init_colors()
        
        # FIX #8: Clear screen properly
        self.screen.clear()
        self.screen.refresh()
        
        # Main loop
        while True:
            # FIX #8: Clear at start of each loop
            self.screen.clear()
            
            try:
                if self.current_screen == "main":
                    screen = MainScreen(self.screen, self.theme, self.config)
                    action = screen.show()
                    
                    if action == "exit":
                        break
                    elif action == "back":
                        if self.screen_stack:
                            self.current_screen = self.screen_stack.pop()
                        else:
                            break
                    elif action in ("wizard", "process"):
                        self.screen_stack.append("main")
                        self.current_screen = "wizards"
                    elif action == "wizards":
                        self.screen_stack.append("main")
                        self.current_screen = "wizards"
                    elif action == "config":
                        self.screen_stack.append("main")
                        self.current_screen = "config"
                    elif action == "plugins":
                        self.screen_stack.append("main")
                        self.current_screen = "plugins"
                    elif action == "web":
                        self.screen_stack.append("main")
                        self.current_screen = "web"
                    elif action == "daemon":
                        self.screen_stack.append("main")
                        self.current_screen = "daemon"
                    elif action == "logs":
                        self.screen_stack.append("main")
                        self.current_screen = "logs"
                    elif action == "about":
                        self.screen_stack.append("main")
                        self.current_screen = "about"
                
                elif self.current_screen == "wizards":
                    screen = WizardsScreen(self.screen, self.theme, self.config)
                    action = screen.show()
                    
                    if action == "back":
                        if self.screen_stack:
                            self.current_screen = self.screen_stack.pop()
                        else:
                            self.current_screen = "main"
                
                elif self.current_screen == "config":
                    screen = ConfigScreen(self.screen, self.theme, self.config)
                    action = screen.show()
                    
                    if action == "back":
                        if self.screen_stack:
                            self.current_screen = self.screen_stack.pop()
                        else:
                            self.current_screen = "main"
                
                elif self.current_screen == "plugins":
                    screen = PluginsScreen(self.screen, self.theme, self.config)
                    action = screen.show()
                    
                    if action == "back":
                        if self.screen_stack:
                            self.current_screen = self.screen_stack.pop()
                        else:
                            self.current_screen = "main"
                
                elif self.current_screen == "web":
                    screen = WebScreen(self.screen, self.theme, self.config)
                    action = screen.show()
                    
                    if action == "back":
                        if self.screen_stack:
                            self.current_screen = self.screen_stack.pop()
                        else:
                            self.current_screen = "main"
                
                elif self.current_screen == "daemon":
                    screen = DaemonScreen(self.screen, self.theme, self.config)
                    action = screen.show()
                    
                    if action == "back":
                        if self.screen_stack:
                            self.current_screen = self.screen_stack.pop()
                        else:
                            self.current_screen = "main"
                
                elif self.current_screen == "logs":
                    screen = LogsScreen(self.screen, self.theme, self.config)
                    action = screen.show()
                    
                    if action == "back":
                        if self.screen_stack:
                            self.current_screen = self.screen_stack.pop()
                        else:
                            self.current_screen = "main"
                
                elif self.current_screen == "about":
                    screen = AboutScreen(self.screen, self.theme, self.config)
                    action = screen.show()
                    
                    if self.screen_stack:
                        self.current_screen = self.screen_stack.pop()
                    else:
                        self.current_screen = "main"
                
                else:
                    # Unknown screen, go back to main
                    self.current_screen = "main"
            
            except Exception as e:
                self.logger.error(f"Screen error: {e}")
                # Go back to main on error
                self.current_screen = "main"
                self.screen_stack.clear()
