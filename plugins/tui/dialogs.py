"""TUI dialogs - confirm, input, message, choice."""

from __future__ import annotations

import curses
from typing import Any

from .theme import Theme


class Dialogs:
    """Dialog manager."""
    
    def __init__(self, screen, theme: Theme):
        """Initialize dialogs.
        
        Args:
            screen: Curses screen
            theme: Theme manager
        """
        self.screen = screen
        self.theme = theme
    
    def message(self, title: str, text: str) -> None:
        """Show message box.
        
        Args:
            title: Message title
            text: Message text
        """
        h, w = self.screen.getmaxyx()
        
        # Calculate dimensions
        lines = text.split('\n')
        box_h = len(lines) + 6
        box_w = min(max(len(line) for line in lines) + 8, w - 10)
        box_y = (h - box_h) // 2
        box_x = (w - box_w) // 2
        
        # Create window
        win = curses.newwin(box_h, box_w, box_y, box_x)
        
        # Draw box
        win.attron(self.theme.get_color_pair(Theme.PAIR_MENU))
        win.box()
        win.attroff(self.theme.get_color_pair(Theme.PAIR_MENU))
        
        # Title
        win.attron(self.theme.get_color_pair(Theme.PAIR_TITLE))
        win.addstr(0, 2, f" {title} ")
        win.attroff(self.theme.get_color_pair(Theme.PAIR_TITLE))
        
        # Text
        for i, line in enumerate(lines):
            win.addstr(2 + i, 2, line)
        
        # Footer
        win.addstr(box_h - 2, 2, "Press any key to continue...")
        
        win.refresh()
        win.getch()
    
    def confirm(self, question: str, default: bool = False) -> bool:
        """Show confirmation dialog.
        
        Args:
            question: Question to ask
            default: Default answer
            
        Returns:
            True if yes, False if no
        """
        h, w = self.screen.getmaxyx()
        
        box_h = 8
        box_w = min(len(question) + 10, w - 10)
        box_y = (h - box_h) // 2
        box_x = (w - box_w) // 2
        
        win = curses.newwin(box_h, box_w, box_y, box_x)
        
        while True:
            win.clear()
            
            # Box
            win.attron(self.theme.get_color_pair(Theme.PAIR_MENU))
            win.box()
            win.attroff(self.theme.get_color_pair(Theme.PAIR_MENU))
            
            # Title
            win.attron(self.theme.get_color_pair(Theme.PAIR_TITLE))
            win.addstr(0, 2, " Confirm ")
            win.attroff(self.theme.get_color_pair(Theme.PAIR_TITLE))
            
            # Question
            win.addstr(2, 2, question[:box_w - 4])
            
            # Options
            if default:
                win.addstr(4, 2, "[Y]es  [n]o")
            else:
                win.addstr(4, 2, "[y]es  [N]o")
            
            win.refresh()
            
            key = win.getch()
            
            if key in (ord('y'), ord('Y')):
                return True
            elif key in (ord('n'), ord('N')):
                return False
            elif key == 27:  # Esc
                return default
            elif key in (curses.KEY_ENTER, 10, 13):
                return default
    
    def input_text(
        self,
        title: str,
        prompt: str,
        default: str = ""
    ) -> str | None:
        """Show text input dialog.
        
        Args:
            title: Dialog title
            prompt: Input prompt
            default: Default value
            
        Returns:
            Input text or None if cancelled
        """
        h, w = self.screen.getmaxyx()
        
        box_h = 10
        box_w = min(60, w - 10)
        box_y = (h - box_h) // 2
        box_x = (w - box_w) // 2
        
        win = curses.newwin(box_h, box_w, box_y, box_x)
        
        # Box
        win.attron(self.theme.get_color_pair(Theme.PAIR_MENU))
        win.box()
        win.attroff(self.theme.get_color_pair(Theme.PAIR_MENU))
        
        # Title
        win.attron(self.theme.get_color_pair(Theme.PAIR_TITLE))
        win.addstr(0, 2, f" {title} ")
        win.attroff(self.theme.get_color_pair(Theme.PAIR_TITLE))
        
        # Prompt
        win.addstr(2, 2, prompt[:box_w - 4])
        
        # Default value
        if default:
            win.addstr(4, 2, f"Default: {default}")
        
        # Input field
        win.addstr(6, 2, "Value:")
        win.addstr(7, 2, "Press Esc to cancel, Enter to confirm")
        
        win.refresh()
        
        # Enable echo and cursor
        curses.echo()
        curses.curs_set(1)
        
        try:
            value = win.getstr(6, 9, box_w - 12).decode('utf-8').strip()
            return value if value else (default if default else None)
        except KeyboardInterrupt:
            return None
        finally:
            curses.noecho()
            curses.curs_set(0)
    
    def choice(
        self,
        title: str,
        prompt: str,
        choices: list[str],
        default: str | None = None
    ) -> str | None:
        """Show choice dialog.
        
        Args:
            title: Dialog title
            prompt: Choice prompt
            choices: List of choices
            default: Default choice
            
        Returns:
            Selected choice or None if cancelled
        """
        h, w = self.screen.getmaxyx()
        
        box_h = len(choices) + 8
        box_w = min(60, w - 10)
        box_y = (h - box_h) // 2
        box_x = (w - box_w) // 2
        
        win = curses.newwin(box_h, box_w, box_y, box_x)
        
        selected = 0
        if default and default in choices:
            selected = choices.index(default)
        
        while True:
            win.clear()
            
            # Box
            win.attron(self.theme.get_color_pair(Theme.PAIR_MENU))
            win.box()
            win.attroff(self.theme.get_color_pair(Theme.PAIR_MENU))
            
            # Title
            win.attron(self.theme.get_color_pair(Theme.PAIR_TITLE))
            win.addstr(0, 2, f" {title} ")
            win.attroff(self.theme.get_color_pair(Theme.PAIR_TITLE))
            
            # Prompt
            win.addstr(2, 2, prompt[:box_w - 4])
            
            # Choices
            for i, choice in enumerate(choices):
                y = 4 + i
                if i == selected:
                    win.attron(self.theme.get_color_pair(Theme.PAIR_SELECTED))
                    win.addstr(y, 4, choice[:box_w - 8].ljust(box_w - 8))
                    win.attroff(self.theme.get_color_pair(Theme.PAIR_SELECTED))
                else:
                    win.addstr(y, 4, choice[:box_w - 8])
            
            # Footer
            win.addstr(box_h - 2, 2, "↑↓: Select | Enter: Confirm | Esc: Cancel")
            
            win.refresh()
            
            key = win.getch()
            
            if key == curses.KEY_UP:
                selected = (selected - 1) % len(choices)
            elif key == curses.KEY_DOWN:
                selected = (selected + 1) % len(choices)
            elif key in (curses.KEY_ENTER, 10, 13):
                return choices[selected]
            elif key == 27:  # Esc
                return None
