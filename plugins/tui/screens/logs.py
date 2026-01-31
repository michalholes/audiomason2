"""Logs viewer screen."""

from __future__ import annotations

from pathlib import Path

from ..menu import Menu, MenuItem
from ..dialogs import Dialogs
from ..theme import Theme


class LogsScreen:
    """Logs viewer screen."""
    
    def __init__(self, screen, theme: Theme, config: dict):
        """Initialize logs screen.
        
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
        """Show logs menu.
        
        Returns:
            Selected action or "back"
        """
        log_dir = Path.home() / ".audiomason" / "logs"
        
        items = [
            MenuItem(
                key="1",
                label="View Latest Log",
                desc="Show most recent log file",
                action="latest",
                visible=True
            ),
            MenuItem(
                key="2",
                label="View All Logs",
                desc="List all log files",
                action="all",
                visible=True
            ),
            MenuItem(
                key="3",
                label="Clear Logs",
                desc="Delete all log files",
                action="clear",
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
            title="View Logs",
            items=items,
            footer="<Select>                                             <Back>"
        )
        
        if action == "latest":
            if log_dir.exists():
                log_files = sorted(log_dir.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
                if log_files:
                    latest = log_files[0]
                    try:
                        content = latest.read_text()
                        # Show last 20 lines
                        lines = content.split('\n')[-20:]
                        self.dialogs.message(
                            f"Latest Log: {latest.name}",
                            "\n".join(lines)
                        )
                    except Exception as e:
                        self.dialogs.message("Error", f"Failed to read log:\n{e}")
                else:
                    self.dialogs.message("No Logs", "No log files found")
            else:
                self.dialogs.message("No Logs", f"Log directory not found:\n{log_dir}")
                
        elif action == "all":
            if log_dir.exists():
                log_files = sorted(log_dir.glob("*.log"))
                if log_files:
                    file_list = "\n".join(f"  - {f.name}" for f in log_files)
                    self.dialogs.message("All Logs", f"Log files:\n\n{file_list}")
                else:
                    self.dialogs.message("No Logs", "No log files found")
            else:
                self.dialogs.message("No Logs", f"Log directory not found:\n{log_dir}")
                
        elif action == "clear":
            if self.dialogs.confirm("Delete all log files?", default=False):
                if log_dir.exists():
                    count = 0
                    for log_file in log_dir.glob("*.log"):
                        log_file.unlink()
                        count += 1
                    self.dialogs.message("Logs Cleared", f"Deleted {count} log file(s)")
                else:
                    self.dialogs.message("No Logs", "No log files to delete")
        
        return action
