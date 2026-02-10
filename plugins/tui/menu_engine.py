"""Ncurses menu engine for TUI plugin.

Raspi-config style visual:
- Blue outer background
- Grey/white window
- Red cursor highlight
- Yellow help bar
"""

from __future__ import annotations

import curses
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

# Color pair IDs
COLOR_NORMAL = 1
COLOR_CURSOR = 2
COLOR_BORDER = 3
COLOR_TITLE = 4
COLOR_HELP = 5
COLOR_ERROR = 6
COLOR_SUCCESS = 7


@dataclass
class MenuItem:
    """Single menu item."""

    id: str
    label: str
    action: Callable[[], str | None] | None = None
    submenu: list[MenuItem] | None = None
    enabled: bool = True
    description: str = ""


class MenuEngine:
    """Ncurses-based menu engine with raspi-config styling."""

    def __init__(self, stdscr: Any) -> None:
        """Initialize menu engine.

        Args:
            stdscr: Curses standard screen
        """
        self.stdscr = stdscr
        self.selected_index = 0
        self.menu_stack: list[tuple[str, list[MenuItem]]] = []
        self.current_title = "Main Menu"
        self.current_items: list[MenuItem] = []
        self.message: tuple[str, int] | None = None  # (text, color_pair)
        self.running = True

        self._init_colors()
        self._init_curses()

    def _init_colors(self) -> None:
        """Initialize ncurses color pairs for raspi-config style."""
        curses.start_color()
        curses.use_default_colors()

        # Raspi-config style colors
        # Normal text: black on white/grey
        curses.init_pair(COLOR_NORMAL, curses.COLOR_BLACK, curses.COLOR_WHITE)
        # Cursor: white on red (selected item)
        curses.init_pair(COLOR_CURSOR, curses.COLOR_WHITE, curses.COLOR_RED)
        # Border/background: white on blue
        curses.init_pair(COLOR_BORDER, curses.COLOR_WHITE, curses.COLOR_BLUE)
        # Title bar: white on red
        curses.init_pair(COLOR_TITLE, curses.COLOR_WHITE, curses.COLOR_RED)
        # Help bar: black on white
        curses.init_pair(COLOR_HELP, curses.COLOR_BLACK, curses.COLOR_WHITE)
        # Error: white on red
        curses.init_pair(COLOR_ERROR, curses.COLOR_WHITE, curses.COLOR_RED)
        # Success: black on green
        curses.init_pair(COLOR_SUCCESS, curses.COLOR_BLACK, curses.COLOR_GREEN)

    def _init_curses(self) -> None:
        """Initialize curses settings."""
        curses.curs_set(0)  # Hide cursor
        self.stdscr.keypad(True)  # Enable special keys
        self.stdscr.timeout(-1)  # Blocking input

    def set_menu(self, title: str, items: list[MenuItem]) -> None:
        """Set current menu.

        Args:
            title: Menu title
            items: Menu items
        """
        self.current_title = title
        self.current_items = items
        self.selected_index = 0

    def push_menu(self, title: str, items: list[MenuItem]) -> None:
        """Push new menu onto stack (enter submenu).

        Args:
            title: Submenu title
            items: Submenu items
        """
        # Save current state
        self.menu_stack.append((self.current_title, self.current_items))
        self.set_menu(title, items)

    def pop_menu(self) -> bool:
        """Pop menu from stack (go back).

        Returns:
            True if popped, False if at root
        """
        if not self.menu_stack:
            return False

        title, items = self.menu_stack.pop()
        self.set_menu(title, items)
        return True

    def show_message(self, text: str, is_error: bool = False) -> None:
        """Show temporary message.

        Args:
            text: Message text
            is_error: True for error style
        """
        color = COLOR_ERROR if is_error else COLOR_SUCCESS
        self.message = (text, color)

    def clear_message(self) -> None:
        """Clear current message."""
        self.message = None

    def draw(self) -> None:
        """Draw the menu screen."""
        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()

        # Fill background with blue
        self.stdscr.bkgd(" ", curses.color_pair(COLOR_BORDER))

        # Calculate window dimensions
        win_width = min(60, width - 4)
        win_height = min(len(self.current_items) + 6, height - 4)
        win_x = (width - win_width) // 2
        win_y = (height - win_height) // 2

        # Draw window background (white/grey)
        for y in range(win_y, win_y + win_height):
            self.stdscr.addstr(y, win_x, " " * win_width, curses.color_pair(COLOR_NORMAL))

        # Draw border
        self._draw_border(win_y, win_x, win_height, win_width)

        # Draw title bar
        title = f" AudioMason v2 - {self.current_title} "
        title_x = win_x + (win_width - len(title)) // 2
        self.stdscr.addstr(win_y, title_x, title, curses.color_pair(COLOR_TITLE))

        # Draw menu items
        item_start_y = win_y + 2
        for i, item in enumerate(self.current_items):
            if i >= win_height - 5:  # Leave room for help bar
                break

            # Item text
            prefix = "[X] " if not item.enabled else "    "
            text = f"{prefix}{item.label}"
            text = text[: win_width - 4]  # Truncate if needed
            text = text.ljust(win_width - 4)

            # Color based on selection
            if i == self.selected_index:
                attr = curses.color_pair(COLOR_CURSOR)
            else:
                attr = curses.color_pair(COLOR_NORMAL)

            self.stdscr.addstr(item_start_y + i, win_x + 2, text, attr)

        # Draw help bar at bottom of window
        help_y = win_y + win_height - 2
        help_text = " Up/Down:Navigate  Enter:Select  Esc:Back  q:Quit "
        help_text = help_text.center(win_width - 2)
        self.stdscr.addstr(help_y, win_x + 1, help_text, curses.color_pair(COLOR_HELP))

        # Draw message if present
        if self.message:
            msg_text, msg_color = self.message
            msg_y = win_y + win_height + 1
            if msg_y < height - 1:
                msg_text = msg_text.center(win_width)
                self.stdscr.addstr(msg_y, win_x, msg_text, curses.color_pair(msg_color))

        self.stdscr.refresh()

    def _draw_border(self, y: int, x: int, h: int, w: int) -> None:
        """Draw box border.

        Args:
            y: Top-left y
            x: Top-left x
            h: Height
            w: Width
        """
        attr = curses.color_pair(COLOR_NORMAL)

        # Corners and edges
        self.stdscr.addch(y, x, curses.ACS_ULCORNER, attr)
        self.stdscr.addch(y, x + w - 1, curses.ACS_URCORNER, attr)
        self.stdscr.addch(y + h - 1, x, curses.ACS_LLCORNER, attr)
        self.stdscr.addch(y + h - 1, x + w - 1, curses.ACS_LRCORNER, attr)

        # Horizontal lines
        for i in range(1, w - 1):
            self.stdscr.addch(y, x + i, curses.ACS_HLINE, attr)
            self.stdscr.addch(y + h - 1, x + i, curses.ACS_HLINE, attr)

        # Vertical lines
        for i in range(1, h - 1):
            self.stdscr.addch(y + i, x, curses.ACS_VLINE, attr)
            self.stdscr.addch(y + i, x + w - 1, curses.ACS_VLINE, attr)

        # Separator below title
        self.stdscr.addch(y + 1, x, curses.ACS_LTEE, attr)
        self.stdscr.addch(y + 1, x + w - 1, curses.ACS_RTEE, attr)
        for i in range(1, w - 1):
            self.stdscr.addch(y + 1, x + i, curses.ACS_HLINE, attr)

    def handle_input(self) -> bool:
        """Handle user input.

        Returns:
            True to continue, False to exit
        """
        key = self.stdscr.getch()

        # Clear message on any key
        self.clear_message()

        if key in (curses.KEY_UP, ord("k")):
            # Move up
            if self.selected_index > 0:
                self.selected_index -= 1
            return True

        elif key in (curses.KEY_DOWN, ord("j")):
            # Move down
            if self.selected_index < len(self.current_items) - 1:
                self.selected_index += 1
            return True

        elif key in (curses.KEY_ENTER, ord("\n"), ord(" ")):
            # Select item
            if self.current_items:
                item = self.current_items[self.selected_index]
                if item.submenu is not None:
                    self.push_menu(item.label, item.submenu)
                elif item.action is not None:
                    result = item.action()
                    if result:
                        self.show_message(result)
            return True

        elif key in (27, ord("q")):  # ESC or q
            # Go back or quit
            if not self.pop_menu():
                self.running = False
            return True

        return True

    def run(self) -> None:
        """Run menu loop."""
        while self.running:
            self.draw()
            if not self.handle_input():
                break

    def confirm_dialog(self, message: str) -> bool:
        """Show yes/no confirmation dialog.

        Args:
            message: Confirmation message

        Returns:
            True if confirmed
        """
        height, width = self.stdscr.getmaxyx()

        # Dialog dimensions
        dialog_width = min(50, width - 4)
        dialog_height = 5
        dialog_x = (width - dialog_width) // 2
        dialog_y = (height - dialog_height) // 2

        # Draw dialog
        for y in range(dialog_y, dialog_y + dialog_height):
            self.stdscr.addstr(y, dialog_x, " " * dialog_width, curses.color_pair(COLOR_NORMAL))

        # Border
        self._draw_border(dialog_y, dialog_x, dialog_height, dialog_width)

        # Message
        msg = message[: dialog_width - 4]
        self.stdscr.addstr(
            dialog_y + 1,
            dialog_x + 2,
            msg.center(dialog_width - 4),
            curses.color_pair(COLOR_NORMAL),
        )

        # Options
        options = "[Y]es  [N]o"
        self.stdscr.addstr(
            dialog_y + 3,
            dialog_x + 2,
            options.center(dialog_width - 4),
            curses.color_pair(COLOR_HELP),
        )

        self.stdscr.refresh()

        # Wait for input
        while True:
            key = self.stdscr.getch()
            if key in (ord("y"), ord("Y")):
                return True
            elif key in (ord("n"), ord("N"), 27):  # ESC = no
                return False
