"""About screen."""

from __future__ import annotations

import sys
import platform

from ..dialogs import Dialogs
from ..theme import Theme


class AboutScreen:
    """About screen."""
    
    def __init__(self, screen, theme: Theme, config: dict):
        """Initialize about screen.
        
        Args:
            screen: Curses screen
            theme: Theme manager
            config: TUI configuration
        """
        self.screen = screen
        self.theme = theme
        self.config = config
        self.dialogs = Dialogs(screen, theme)
    
    def show(self) -> str:
        """Show about information.
        
        Returns:
            Always returns "back"
        """
        # Get system info
        py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        os_info = platform.platform()
        
        info = f"""AudioMason v2.0.0-alpha

Ultra-modular audiobook processing system

Author: Michal Holeš
License: MIT
Homepage: https://github.com/michalholes/audiomason2

System Information:
  Python: {py_version}
  Platform: {os_info}

Press any key to return..."""
        
        self.dialogs.message("About AudioMason", info)
        
        return "back"
