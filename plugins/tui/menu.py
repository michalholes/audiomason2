"""TUI menu rendering engine - raspi-config style."""

from __future__ import annotations

import curses
from typing import Any

from .theme import Theme


class MenuItem:
    """Menu item."""
    
    def __init__(
        self,
        key: str,
        label: str,
        desc: str = "",
        action: str = "",
        visible: bool = True
    ):
        """Initialize menu item.
        
        Args:
            key: Hotkey
            label: Item label
            desc: Item description
            action: Action to perform
            visible: Whether item is visible
        """
        self.key = key
        self.label = label
        self.desc = desc
        self.action = action
        self.visible = visible


class Menu:
    """Menu renderer."""
    
    def __init__(self, screen, theme: Theme):
        """Initialize menu.
        
        Args:
            screen: Curses screen
            theme: Theme manager
        """
        self.screen = screen
        self.theme = theme
        self.selected = 0
    
    def draw_box(
        self,
        y: int,
        x: int,
        height: int,
        width: int,
        title: str = ""
    ) -> None:
        """Draw a box with optional title (raspi-config style).
        
        Args:
            y: Y position
            x: X position
            height: Box height
            width: Box width
            title: Optional title
        """
        # Draw title bar (red background)
        self.screen.attron(self.theme.get_color_pair(Theme.PAIR_TITLE))
        title_text = f" {title} " if title else " " * width
        # Center title
        padding = (width - len(title_text)) // 2
        full_title = " " * padding + title_text + " " * (width - padding - len(title_text))
        self.screen.addstr(y, x, full_title[:width])
        self.screen.attroff(self.theme.get_color_pair(Theme.PAIR_TITLE))
        
        # Draw menu area (gray background)
        self.screen.attron(self.theme.get_color_pair(Theme.PAIR_MENU))
        
        # Draw horizontal line under title
        self.screen.addstr(y + 1, x, "─" * width)
        
        # Draw menu body
        for i in range(2, height - 1):
            self.screen.addstr(y + i, x, " " * width)
        
        # Draw bottom line
        self.screen.addstr(y + height - 1, x, " " * width)
        
        self.screen.attroff(self.theme.get_color_pair(Theme.PAIR_MENU))
    
    def draw_menu_items(
        self,
        y: int,
        x: int,
        width: int,
        items: list[MenuItem],
        selected: int
    ) -> None:
        """Draw menu items (double-column raspi-config style).
        
        Args:
            y: Start Y position
            x: Start X position
            width: Menu width
            items: Menu items
            selected: Selected item index
        """
        visible_items = [item for item in items if item.visible]
        
        for i, item in enumerate(visible_items):
            item_y = y + i
            
            # Format: "  1  Process Files          Import and convert audiobooks"
            # Key takes 4 chars, label takes ~25 chars, desc takes rest
            label_width = 28
            desc_width = width - label_width - 8
            
            key_part = f"  {item.key}  "
            label_part = item.label.ljust(label_width)[:label_width]
            desc_part = item.desc[:desc_width] if item.desc else ""
            
            full_line = key_part + label_part + desc_part
            full_line = full_line.ljust(width)[:width]
            
            if i == selected:
                # Selected item (white background, black text)
                self.screen.attron(self.theme.get_color_pair(Theme.PAIR_SELECTED))
                self.screen.addstr(item_y, x, full_line)
                self.screen.attroff(self.theme.get_color_pair(Theme.PAIR_SELECTED))
            else:
                # Normal item (gray background, black text)
                self.screen.attron(self.theme.get_color_pair(Theme.PAIR_MENU))
                self.screen.addstr(item_y, x, full_line)
                self.screen.attroff(self.theme.get_color_pair(Theme.PAIR_MENU))
    
    def draw_footer(
        self,
        y: int,
        x: int,
        width: int,
        text: str = "<Select>                                             <Finish>"
    ) -> None:
        """Draw footer (raspi-config style).
        
        Args:
            y: Y position
            x: X position
            width: Footer width
            text: Footer text
        """
        # Draw in menu colors
        self.screen.attron(self.theme.get_color_pair(Theme.PAIR_MENU))
        footer = text.ljust(width)[:width]
        self.screen.addstr(y, x, footer)
        self.screen.attroff(self.theme.get_color_pair(Theme.PAIR_MENU))
    
    def show(
        self,
        title: str,
        items: list[MenuItem],
        footer: str = "<Select>                                             <Finish>"
    ) -> str:
        """Show menu and handle input.
        
        Args:
            title: Menu title
            items: Menu items
            footer: Footer text
            
        Returns:
            Selected action or "back"
        """
        visible_items = [item for item in items if item.visible]
        selected = 0
        
        while True:
            self.screen.clear()
            h, w = self.screen.getmaxyx()
            
            # Calculate dimensions
            box_height = len(visible_items) + 4  # +4 for title, separator, footer
            box_width = w - 4
            box_y = 2
            box_x = 2
            
            # Draw box
            self.draw_box(box_y, box_x, box_height, box_width, title)
            
            # Draw menu items
            self.draw_menu_items(
                box_y + 2,
                box_x,
                box_width,
                items,
                selected
            )
            
            # Draw footer
            self.draw_footer(
                box_y + box_height - 1,
                box_x,
                box_width,
                footer
            )
            
            self.screen.refresh()
            
            # Handle input
            key = self.screen.getch()
            
            if key == curses.KEY_UP:
                selected = (selected - 1) % len(visible_items)
            elif key == curses.KEY_DOWN:
                selected = (selected + 1) % len(visible_items)
            elif key in (curses.KEY_ENTER, 10, 13):
                return visible_items[selected].action
            elif key == 27:  # Esc
                return "back"
            else:
                # Check for number key shortcuts
                ch = chr(key) if 32 <= key <= 126 else None
                if ch:
                    for idx, item in enumerate(visible_items):
                        if item.key == ch:
                            return item.action
