"""TUI plugin - Terminal User Interface (all-in-one).

Raspi-config style ncurses menu system.
All components in one file to avoid import issues.

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
import platform
import sys
from pathlib import Path
from typing import Any

import yaml

from audiomason.core.logging import get_logger, set_verbosity

try:
    import curses

    HAS_CURSES = True
except ImportError:
    HAS_CURSES = False


# ============================================================================
# THEME SYSTEM
# ============================================================================

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
    "lightgray": curses.COLOR_WHITE,
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
        """Initialize theme."""
        self.config = config or {}
        self._colors = self._load_colors()

    def _load_colors(self) -> dict[str, int]:
        """Load color scheme based on config."""
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
        """Load custom color scheme from config."""
        custom = self.config.get("custom_theme", {})
        colors = {}

        for key, default in RASPI_CONFIG_THEME.items():
            color_name = custom.get(key, "").lower()
            colors[key] = COLOR_NAMES.get(color_name, default)

        return colors

    def init_colors(self) -> None:
        """Initialize curses color pairs."""
        curses.init_pair(self.PAIR_TITLE, self._colors["title_fg"], self._colors["title_bg"])
        curses.init_pair(self.PAIR_MENU, self._colors["menu_fg"], self._colors["menu_bg"])
        curses.init_pair(
            self.PAIR_SELECTED, self._colors["selected_fg"], self._colors["selected_bg"]
        )
        curses.init_pair(self.PAIR_SUCCESS, self._colors["success_fg"], curses.COLOR_BLACK)
        curses.init_pair(self.PAIR_ERROR, self._colors["error_fg"], curses.COLOR_BLACK)

    def get_color_pair(self, pair_id: int) -> int:
        """Get curses color pair."""
        return curses.color_pair(pair_id)


# ============================================================================
# MENU SYSTEM
# ============================================================================


class MenuItem:
    """Menu item."""

    def __init__(
        self, key: str, label: str, desc: str = "", action: str = "", visible: bool = True
    ):
        """Initialize menu item."""
        self.key = key
        self.label = label
        self.desc = desc
        self.action = action
        self.visible = visible


class Menu:
    """Menu renderer."""

    def __init__(self, screen, theme: Theme, logger=None):
        """Initialize menu."""
        self.screen = screen
        self.theme = theme
        self.selected = 0
        self.logger = logger

    def draw_box(self, y: int, x: int, height: int, width: int, title: str = "") -> None:
        """Draw a box with optional title (raspi-config style)."""
        # Draw title bar (red background)
        self.screen.attron(self.theme.get_color_pair(Theme.PAIR_TITLE))
        title_text = f" {title} " if title else " " * width
        padding = (width - len(title_text)) // 2
        full_title = " " * padding + title_text + " " * (width - padding - len(title_text))
        self.screen.addstr(y, x, full_title[:width])
        self.screen.attroff(self.theme.get_color_pair(Theme.PAIR_TITLE))

        # Draw menu area (gray background)
        self.screen.attron(self.theme.get_color_pair(Theme.PAIR_MENU))
        self.screen.addstr(y + 1, x, "─" * width)

        for i in range(2, height - 1):
            self.screen.addstr(y + i, x, " " * width)

        self.screen.addstr(y + height - 1, x, " " * width)
        self.screen.attroff(self.theme.get_color_pair(Theme.PAIR_MENU))

    def draw_menu_items(
        self, y: int, x: int, width: int, items: list[MenuItem], selected: int
    ) -> None:
        """Draw menu items (double-column raspi-config style)."""
        visible_items = [item for item in items if item.visible]

        for i, item in enumerate(visible_items):
            item_y = y + i

            label_width = 28
            desc_width = width - label_width - 8

            key_part = f"  {item.key}  "
            label_part = item.label.ljust(label_width)[:label_width]
            desc_part = item.desc[:desc_width] if item.desc else ""

            full_line = key_part + label_part + desc_part
            full_line = full_line.ljust(width)[:width]

            if i == selected:
                self.screen.attron(self.theme.get_color_pair(Theme.PAIR_SELECTED))
                self.screen.addstr(item_y, x, full_line)
                self.screen.attroff(self.theme.get_color_pair(Theme.PAIR_SELECTED))
            else:
                self.screen.attron(self.theme.get_color_pair(Theme.PAIR_MENU))
                self.screen.addstr(item_y, x, full_line)
                self.screen.attroff(self.theme.get_color_pair(Theme.PAIR_MENU))

    def draw_footer(
        self,
        y: int,
        x: int,
        width: int,
        text: str = "<Select>                                             <Finish>",
    ) -> None:
        """Draw footer (raspi-config style)."""
        self.screen.attron(self.theme.get_color_pair(Theme.PAIR_MENU))
        footer = text.ljust(width)[:width]
        self.screen.addstr(y, x, footer)
        self.screen.attroff(self.theme.get_color_pair(Theme.PAIR_MENU))

    def show(
        self,
        title: str,
        items: list[MenuItem],
        footer: str = "<Select>                                             <Finish>",
    ) -> str:
        """Show menu and handle input."""
        visible_items = [item for item in items if item.visible]
        selected = 0

        while True:
            self.screen.clear()

            # CRITICAL: Enable keypad AFTER clear (clear resets it!)
            self.screen.keypad(True)

            h, w = self.screen.getmaxyx()

            box_height = len(visible_items) + 4
            box_width = w - 4
            box_y = 2
            box_x = 2

            self.draw_box(box_y, box_x, box_height, box_width, title)
            self.draw_menu_items(box_y + 2, box_x, box_width, items, selected)
            self.draw_footer(box_y + box_height - 1, box_x, box_width, footer)

            self.screen.refresh()

            key = self.screen.getch()

            # DEBUG: Log key codes to see what's coming through
            from audiomason.core.logging import get_logger

            logger = get_logger("tui.menu")
            logger.debug(f"Key pressed: {key} (UP={curses.KEY_UP}, DOWN={curses.KEY_DOWN})")

            if key == curses.KEY_UP:
                selected = (selected - 1) % len(visible_items)
            elif key == curses.KEY_DOWN:
                selected = (selected + 1) % len(visible_items)
            elif key in (curses.KEY_ENTER, 10, 13):
                return visible_items[selected].action
            elif key == 27:  # Esc
                return "back"
            else:
                ch = chr(key) if 32 <= key <= 126 else None
                if ch:
                    for _, item in enumerate(visible_items):
                        if item.key == ch:
                            return item.action


# ============================================================================
# DIALOGS
# ============================================================================


class Dialogs:
    """Dialog manager."""

    def __init__(self, screen, theme: Theme):
        """Initialize dialogs."""
        self.screen = screen
        self.theme = theme

    def message(self, title: str, text: str) -> None:
        """Show message box."""
        h, w = self.screen.getmaxyx()

        lines = text.split("\n")
        box_h = len(lines) + 6
        box_w = min(max(len(line) for line in lines) + 8, w - 10)
        box_y = (h - box_h) // 2
        box_x = (w - box_w) // 2

        win = curses.newwin(box_h, box_w, box_y, box_x)
        win.keypad(True)

        win.attron(self.theme.get_color_pair(Theme.PAIR_MENU))
        win.box()
        win.attroff(self.theme.get_color_pair(Theme.PAIR_MENU))

        win.attron(self.theme.get_color_pair(Theme.PAIR_TITLE))
        win.addstr(0, 2, f" {title} ")
        win.attroff(self.theme.get_color_pair(Theme.PAIR_TITLE))

        for i, line in enumerate(lines):
            win.addstr(2 + i, 2, line)

        win.addstr(box_h - 2, 2, "Press any key to continue...")

        win.refresh()
        win.getch()

    def confirm(self, question: str, default: bool = False) -> bool:
        """Show confirmation dialog."""
        h, w = self.screen.getmaxyx()

        box_h = 8
        box_w = min(len(question) + 10, w - 10)
        box_y = (h - box_h) // 2
        box_x = (w - box_w) // 2

        win = curses.newwin(box_h, box_w, box_y, box_x)

        while True:
            win.clear()

            # CRITICAL: Enable keypad AFTER clear
            win.keypad(True)

            win.attron(self.theme.get_color_pair(Theme.PAIR_MENU))
            win.box()
            win.attroff(self.theme.get_color_pair(Theme.PAIR_MENU))

            win.attron(self.theme.get_color_pair(Theme.PAIR_TITLE))
            win.addstr(0, 2, " Confirm ")
            win.attroff(self.theme.get_color_pair(Theme.PAIR_TITLE))

            win.addstr(2, 2, question[: box_w - 4])

            if default:
                win.addstr(4, 2, "[Y]es  [n]o")
            else:
                win.addstr(4, 2, "[y]es  [N]o")

            win.refresh()

            key = win.getch()

            if key in (ord("y"), ord("Y")):
                return True
            elif key in (ord("n"), ord("N")):
                return False
            elif key == 27 or key in (curses.KEY_ENTER, 10, 13):  # Esc
                return default

    def input_text(self, title: str, prompt: str, default: str = "") -> str | None:
        """Show text input dialog."""
        h, w = self.screen.getmaxyx()

        box_h = 10
        box_w = min(60, w - 10)
        box_y = (h - box_h) // 2
        box_x = (w - box_w) // 2

        win = curses.newwin(box_h, box_w, box_y, box_x)
        win.keypad(True)

        win.attron(self.theme.get_color_pair(Theme.PAIR_MENU))
        win.box()
        win.attroff(self.theme.get_color_pair(Theme.PAIR_MENU))

        win.attron(self.theme.get_color_pair(Theme.PAIR_TITLE))
        win.addstr(0, 2, f" {title} ")
        win.attroff(self.theme.get_color_pair(Theme.PAIR_TITLE))

        win.addstr(2, 2, prompt[: box_w - 4])

        if default:
            win.addstr(4, 2, f"Default: {default}")

        win.addstr(6, 2, "Value:")
        win.addstr(7, 2, "Press Esc to cancel, Enter to confirm")

        win.refresh()

        curses.echo()
        curses.curs_set(1)

        try:
            value = win.getstr(6, 9, box_w - 12).decode("utf-8").strip()
            return value if value else (default if default else None)
        except KeyboardInterrupt:
            return None
        finally:
            curses.noecho()
            curses.curs_set(0)

    def choice(
        self, title: str, prompt: str, choices: list[str], default: str | None = None
    ) -> str | None:
        """Show choice dialog."""
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

            # CRITICAL: Enable keypad AFTER clear
            win.keypad(True)

            win.attron(self.theme.get_color_pair(Theme.PAIR_MENU))
            win.box()
            win.attroff(self.theme.get_color_pair(Theme.PAIR_MENU))

            win.attron(self.theme.get_color_pair(Theme.PAIR_TITLE))
            win.addstr(0, 2, f" {title} ")
            win.attroff(self.theme.get_color_pair(Theme.PAIR_TITLE))

            win.addstr(2, 2, prompt[: box_w - 4])

            for i, choice in enumerate(choices):
                y = 4 + i
                if i == selected:
                    win.attron(self.theme.get_color_pair(Theme.PAIR_SELECTED))
                    win.addstr(y, 4, choice[: box_w - 8].ljust(box_w - 8))
                    win.attroff(self.theme.get_color_pair(Theme.PAIR_SELECTED))
                else:
                    win.addstr(y, 4, choice[: box_w - 8])

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


# ============================================================================
# SCREENS
# ============================================================================


class MainScreen:
    """Main menu screen."""

    def __init__(self, screen, theme: Theme, config: dict):
        """Initialize main screen."""
        self.screen = screen
        self.theme = theme
        self.config = config
        self.menu = Menu(screen, theme)
        self.dialogs = Dialogs(screen, theme)

    def show(self) -> str:
        """Show main menu."""
        # Default menu items
        default_menu = [
            {
                "key": "1",
                "label": "Process Files",
                "desc": "Import and convert audiobooks",
                "action": "process",
                "visible": True,
            },
            {
                "key": "2",
                "label": "Run Wizard",
                "desc": "Execute YAML-based processing wizard",
                "action": "wizard",
                "visible": True,
            },
            {
                "key": "3",
                "label": "Manage Plugins",
                "desc": "Enable/disable/configure plugins",
                "action": "plugins",
                "visible": True,
            },
            {
                "key": "4",
                "label": "Manage Wizards",
                "desc": "Create/edit/run YAML wizards",
                "action": "wizards",
                "visible": True,
            },
            {
                "key": "5",
                "label": "Configuration",
                "desc": "Edit AudioMason settings",
                "action": "config",
                "visible": True,
            },
            {
                "key": "6",
                "label": "Web Server",
                "desc": "Start/stop web interface",
                "action": "web",
                "visible": True,
            },
            {
                "key": "7",
                "label": "Daemon Mode",
                "desc": "Background folder watching",
                "action": "daemon",
                "visible": True,
            },
            {
                "key": "8",
                "label": "View Logs",
                "desc": "Show processing logs",
                "action": "logs",
                "visible": True,
            },
            {
                "key": "9",
                "label": "About",
                "desc": "Version and system information",
                "action": "about",
                "visible": True,
            },
            {
                "key": "0",
                "label": "Exit",
                "desc": "Quit AudioMason",
                "action": "exit",
                "visible": True,
            },
        ]

        items = []
        menu_config = self.config.get("main_menu", default_menu)

        for item_cfg in menu_config:
            items.append(
                MenuItem(
                    key=item_cfg["key"],
                    label=item_cfg["label"],
                    desc=item_cfg["desc"],
                    action=item_cfg["action"],
                    visible=item_cfg.get("visible", True),
                )
            )

        # Add verbosity indicator to title
        verbosity = self.config.get("verbosity", 1)
        verbosity_text = ""
        if verbosity == 0:
            verbosity_text = " [QUIET]"
        elif verbosity == 2:
            verbosity_text = " [VERBOSE]"
        elif verbosity == 3:
            verbosity_text = " [DEBUG]"

        title = f"AudioMason v2 - Main Menu{verbosity_text}"

        return self.menu.show(
            title=title,
            items=items,
            footer="<Select>                                             <Finish>",
        )


class WizardsScreen:
    """Wizards management screen - FIX #10."""

    def __init__(self, screen, theme: Theme, config: dict):
        """Initialize wizards screen."""
        self.screen = screen
        self.theme = theme
        self.config = config
        self.menu = Menu(screen, theme)
        self.dialogs = Dialogs(screen, theme)

    def _count_wizard_steps(self, wizard_path: Path) -> int:
        """Count steps in wizard YAML - FIX #10."""
        try:
            with open(wizard_path) as f:
                data = yaml.safe_load(f)

            wizard = data.get("wizard", {})
            steps = wizard.get("steps", [])

            if isinstance(steps, list):
                return len(steps)
            else:
                return 0
        except Exception:
            return 0

    def show(self) -> str:
        """Show wizards menu."""
        wizards_dir = Path(__file__).parent.parent.parent / "wizards"

        if not wizards_dir.exists():
            self.dialogs.message("No Wizards", f"Wizards directory not found:\n{wizards_dir}")
            return "back"

        wizard_files = sorted(wizards_dir.glob("*.yaml"))

        if not wizard_files:
            self.dialogs.message(
                "No Wizards", "No wizard files found.\n\nCreate wizards in:\n" + str(wizards_dir)
            )
            return "back"

        items = []
        for i, wizard_file in enumerate(wizard_files):
            try:
                with open(wizard_file) as f:
                    wizard_data = yaml.safe_load(f)

                wizard = wizard_data.get("wizard", {})
                name = wizard.get("name", wizard_file.stem)
                desc = wizard.get("description", "")

                steps = self._count_wizard_steps(wizard_file)

                items.append(
                    MenuItem(
                        key=str(i + 1),
                        label=f"{name} ({steps} steps)",
                        desc=desc[:50],
                        action=f"manage:{wizard_file.stem}",
                        visible=True,
                    )
                )
            except Exception as e:
                items.append(
                    MenuItem(
                        key=str(i + 1),
                        label=f"{wizard_file.stem} (error)",
                        desc=str(e)[:50],
                        action="",
                        visible=True,
                    )
                )

        items.append(
            MenuItem(key="0", label="Back", desc="Return to main menu", action="back", visible=True)
        )

        action = self.menu.show(
            title="Wizard Management",
            items=items,
            footer="<Select>                                             <Back>",
        )

        if action.startswith("manage:"):
            wizard_name = action[7:]
            self._manage_wizard(wizard_name, wizards_dir)
            return "wizards"  # Refresh screen

        return action

    def _manage_wizard(self, wizard_name: str, wizards_dir: Path) -> None:
        """Manage a specific wizard."""
        wizard_file = wizards_dir / f"{wizard_name}.yaml"

        # Show management menu
        items = [
            MenuItem("1", "Run", "Execute this wizard", "run", True),
            MenuItem("2", "Edit", "Edit wizard YAML", "edit", True),
            MenuItem("3", "View", "View wizard details", "view", True),
            MenuItem("4", "Delete", "Remove this wizard", "delete", True),
            MenuItem("0", "Back", "Return to wizards list", "back", True),
        ]

        action = self.menu.show(
            title=f"Manage: {wizard_name}",
            items=items,
            footer="<Select>                                             <Back>",
        )

        if action == "run":
            if self.dialogs.confirm(f"Run wizard '{wizard_name}'?", default=True):
                self.dialogs.message(
                    "Running Wizard", f"Exit TUI and run:\n\n  audiomason wizard {wizard_name}"
                )

        elif action == "edit":
            self.dialogs.message(
                "Edit Wizard",
                f"Open in editor:\n\n  nano {wizard_file}\n\n"
                f"Or use your preferred editor:\n"
                f"  vim {wizard_file}\n"
                f"  code {wizard_file}",
            )

        elif action == "view":
            try:
                with open(wizard_file) as f:
                    wizard_data = yaml.safe_load(f)

                wizard = wizard_data.get("wizard", {})
                name = wizard.get("name", wizard_name)
                desc = wizard.get("description", "N/A")
                steps = wizard.get("steps", [])

                info = f"Name: {name}\n"
                info += f"Description: {desc}\n"
                info += f"Steps: {len(steps) if isinstance(steps, list) else 0}\n"
                info += f"File: {wizard_file}"

                self.dialogs.message("Wizard Info", info)
            except Exception as e:
                self.dialogs.message("Error", f"Failed to read wizard:\n{e}")

        if action == "delete" and self.dialogs.confirm(
            f"DELETE wizard '{wizard_name}'?\n\nThis cannot be undone!", default=False
        ):
            try:
                wizard_file.unlink()
                self.dialogs.message("Wizard Deleted", f"Wizard '{wizard_name}' has been removed.")
            except Exception as e:
                self.dialogs.message("Error", f"Failed to delete wizard:\n{e}")


class ConfigScreen:
    """Configuration screen - FIX #3, #4, #5, #7."""

    def __init__(self, screen, theme: Theme, config: dict):
        """Initialize config screen."""
        self.screen = screen
        self.theme = theme
        self.config = config
        self.menu = Menu(screen, theme)
        self.dialogs = Dialogs(screen, theme)

        self.config_file = Path.home() / ".config" / "audiomason" / "config.yaml"
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from file."""
        if self.config_file.exists():
            try:
                with open(self.config_file) as f:
                    self.current_config = yaml.safe_load(f) or {}
            except Exception:
                self.current_config = {}
        else:
            self.current_config = {}

    def _save_config(self) -> None:
        """Save configuration to file."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w") as f:
            yaml.safe_dump(self.current_config, f, default_flow_style=False)

    def show(self) -> str:
        """Show configuration menu."""
        items = [
            MenuItem(
                "1",
                "Input Directory",
                self.current_config.get("input_dir", "~/Audiobooks/input"),
                "edit:input_dir",
                True,
            ),
            MenuItem(
                "2",
                "Output Directory",
                self.current_config.get("output_dir", "~/Audiobooks/output"),
                "edit:output_dir",
                True,
            ),
            MenuItem(
                "3", "Bitrate", self.current_config.get("bitrate", "128k"), "edit:bitrate", True
            ),
            MenuItem(
                "4",
                "Loudness Normalization",
                "Enabled" if self.current_config.get("loudnorm", False) else "Disabled",
                "edit:loudnorm",
                True,
            ),
            MenuItem(
                "5",
                "Split Chapters",
                "Enabled" if self.current_config.get("split_chapters", False) else "Disabled",
                "edit:split_chapters",
                True,
            ),
            MenuItem("6", "Daemon Settings", "Configure daemon mode", "daemon", True),
            MenuItem("7", "Web Server Settings", "Configure web server", "web", True),
            MenuItem("0", "Back", "Return to main menu", "back", True),
        ]

        while True:
            items[0].desc = self.current_config.get("input_dir", "~/Audiobooks/input")
            items[1].desc = self.current_config.get("output_dir", "~/Audiobooks/output")
            items[2].desc = self.current_config.get("bitrate", "128k")
            items[3].desc = "Enabled" if self.current_config.get("loudnorm", False) else "Disabled"
            items[4].desc = (
                "Enabled" if self.current_config.get("split_chapters", False) else "Disabled"
            )

            action = self.menu.show(
                title="Configuration",
                items=items,
                footer="<Select>                                             <Back>",
            )

            if action == "back":
                return "back"
            elif action == "daemon":
                self._edit_daemon_settings()
            elif action == "web":
                self._edit_web_settings()
            elif action.startswith("edit:"):
                key = action[5:]
                self._edit_config_value(key)

    def _edit_config_value(self, key: str) -> None:
        """Edit configuration value - FIX #3, #4."""
        if key == "bitrate":
            current = self.current_config.get("bitrate", "128k")
            choices = ["96k", "128k", "192k", "256k", "320k"]

            result = self.dialogs.choice(
                "Select Bitrate", "Choose default audio bitrate:", choices, current
            )

            if result:
                self.current_config["bitrate"] = result
                self._save_config()

        elif key == "loudnorm":
            current = self.current_config.get("loudnorm", False)
            result = self.dialogs.confirm("Enable loudness normalization?", default=current)
            self.current_config["loudnorm"] = result
            self._save_config()

        elif key == "split_chapters":
            current = self.current_config.get("split_chapters", False)
            result = self.dialogs.confirm("Enable chapter splitting?", default=current)
            self.current_config["split_chapters"] = result
            self._save_config()

        elif key in ("input_dir", "output_dir"):
            current = self.current_config.get(key, "")
            result = self.dialogs.input_text(
                f"Edit {key.replace('_', ' ').title()}", "Enter path:", current
            )

            if result:
                self.current_config[key] = result
                self._save_config()

    def _edit_daemon_settings(self) -> None:
        """Edit daemon settings - FIX #5, #7."""
        daemon_config = self.current_config.get("daemon", {})

        items = [
            MenuItem(
                "1",
                "Watch Folders",
                f"{len(daemon_config.get('watch_folders', []))} folders",
                "watch_folders",
                True,
            ),
            MenuItem(
                "2",
                "Check Interval",
                f"{daemon_config.get('interval', 30)} seconds",
                "interval",
                True,
            ),
            MenuItem(
                "3",
                "On Success",
                daemon_config.get("on_success", "move_to_output"),
                "on_success",
                True,
            ),
            MenuItem(
                "4", "On Error", daemon_config.get("on_error", "move_to_error"), "on_error", True
            ),
            MenuItem("0", "Back", "Return to configuration", "back", True),
        ]

        while True:
            daemon_config = self.current_config.get("daemon", {})
            items[0].desc = f"{len(daemon_config.get('watch_folders', []))} folders"
            items[1].desc = f"{daemon_config.get('interval', 30)} seconds"
            items[2].desc = daemon_config.get("on_success", "move_to_output")
            items[3].desc = daemon_config.get("on_error", "move_to_error")

            action = self.menu.show(
                title="Daemon Configuration",
                items=items,
                footer="<Select>                                             <Back>",
            )

            if action == "back":
                return
            elif action == "watch_folders":
                daemon_config = self.current_config.setdefault("daemon", {})
                folders = daemon_config.get("watch_folders", [])

                if folders:
                    folder_list = "\n".join(f"  - {f}" for f in folders)
                    msg = f"Current watch folders:\n\n{folder_list}\n\nAdd or remove?"
                else:
                    msg = (
                        "No watch folders configured.\n\n"
                        "These are directories that daemon monitors\n"
                        "for new audiobook files."
                    )

                self.dialogs.message("Watch Folders", msg)

                result = self.dialogs.input_text(
                    "Add Watch Folder", "Enter folder path (or leave empty):", ""
                )

                if result and result not in folders:
                    folders.append(result)
                    daemon_config["watch_folders"] = folders
                    self._save_config()
            elif action == "interval":
                daemon_config = self.current_config.setdefault("daemon", {})
                current = daemon_config.get("interval", 30)

                result = self.dialogs.input_text(
                    "Check Interval",
                    "How often to check for new files (seconds):\n(Recommended: 30-300)",
                    str(current),
                )

                if result:
                    try:
                        interval = int(result)
                        if 5 <= interval <= 3600:
                            daemon_config["interval"] = interval
                            self._save_config()
                        else:
                            self.dialogs.message(
                                "Invalid Value", "Interval must be between 5 and 3600 seconds"
                            )
                    except ValueError:
                        self.dialogs.message("Invalid Value", "Please enter a number")
            elif action == "on_success":
                daemon_config = self.current_config.setdefault("daemon", {})
                current = daemon_config.get("on_success", "move_to_output")

                result = self.dialogs.choice(
                    "On Success Action",
                    "What to do with source files after successful processing?",
                    ["move_to_output", "keep", "delete"],
                    current,
                )

                if result:
                    daemon_config["on_success"] = result
                    self._save_config()
            elif action == "on_error":
                daemon_config = self.current_config.setdefault("daemon", {})
                current = daemon_config.get("on_error", "move_to_error")

                result = self.dialogs.choice(
                    "On Error Action",
                    "What to do with files that failed to process?",
                    ["move_to_error", "keep", "delete"],
                    current,
                )

                if result:
                    daemon_config["on_error"] = result
                    self._save_config()

    def _edit_web_settings(self) -> None:
        """Edit web server settings."""
        web_config = self.current_config.setdefault("web_server", {})

        items = [
            MenuItem("1", "Host", web_config.get("host", "0.0.0.0"), "host", True),
            MenuItem("2", "Port", str(web_config.get("port", 8080)), "port", True),
            MenuItem("0", "Back", "Return to configuration", "back", True),
        ]

        while True:
            web_config = self.current_config.get("web_server", {})
            items[0].desc = web_config.get("host", "0.0.0.0")
            items[1].desc = str(web_config.get("port", 8080))

            action = self.menu.show(
                title="Web Server Configuration",
                items=items,
                footer="<Select>                                             <Back>",
            )

            if action == "back":
                return
            elif action == "host":
                result = self.dialogs.input_text(
                    "Edit Host", "Enter host address:", web_config.get("host", "0.0.0.0")
                )
                if result:
                    web_config["host"] = result
                    self._save_config()
            elif action == "port":
                result = self.dialogs.input_text(
                    "Edit Port", "Enter port number:", str(web_config.get("port", 8080))
                )
                if result:
                    try:
                        port = int(result)
                        if 1024 <= port <= 65535:
                            web_config["port"] = port
                            self._save_config()
                        else:
                            self.dialogs.message(
                                "Invalid Port", "Port must be between 1024 and 65535"
                            )
                    except ValueError:
                        self.dialogs.message("Invalid Port", "Please enter a number")


class PluginsScreen:
    """Plugins management screen."""

    def __init__(self, screen, theme: Theme, config: dict):
        """Initialize plugins screen."""
        self.screen = screen
        self.theme = theme
        self.config = config
        self.menu = Menu(screen, theme)
        self.dialogs = Dialogs(screen, theme)

    def show(self) -> str:
        """Show plugins menu."""
        plugins_dir = Path(__file__).parent.parent

        plugin_dirs = [
            d for d in plugins_dir.iterdir() if d.is_dir() and (d / "plugin.yaml").exists()
        ]

        items = []
        for i, plugin_dir in enumerate(sorted(plugin_dirs)):
            # Check if plugin is enabled (check config or default to enabled)
            enabled = self._is_plugin_enabled(plugin_dir.name)
            status = "+ Enabled" if enabled else "- Disabled"

            items.append(
                MenuItem(
                    str(i + 1),
                    f"{plugin_dir.name} ({status})",
                    "Click to manage",
                    f"plugin:{plugin_dir.name}",
                    True,
                )
            )

        items.append(MenuItem("0", "Back", "Return to main menu", "back", True))

        action = self.menu.show(
            title="Plugin Management",
            items=items,
            footer="<Select>                                             <Back>",
        )

        if action.startswith("plugin:"):
            plugin_name = action[7:]
            self._manage_plugin(plugin_name)
            return "plugins"  # Refresh screen

        return action

    def _is_plugin_enabled(self, plugin_name: str) -> bool:
        """Check if plugin is enabled."""
        # For now, all plugins are enabled (TODO: read from config)
        return True

    def _manage_plugin(self, plugin_name: str) -> None:
        """Manage a specific plugin."""
        enabled = self._is_plugin_enabled(plugin_name)

        # Show management menu
        items = []

        if enabled:
            items.append(MenuItem("1", "Disable", "Disable this plugin", "disable", True))
        else:
            items.append(MenuItem("2", "Enable", "Enable this plugin", "enable", True))

        items.append(MenuItem("3", "Configure", "Edit plugin configuration", "configure", True))
        items.append(MenuItem("4", "View Info", "View plugin details", "info", True))
        items.append(MenuItem("5", "Delete", "Remove this plugin", "delete", True))
        items.append(MenuItem("0", "Back", "Return to plugins list", "back", True))

        action = self.menu.show(
            title=f"Manage: {plugin_name}",
            items=items,
            footer="<Select>                                             <Back>",
        )

        if action == "disable":
            if self.dialogs.confirm(f"Disable plugin '{plugin_name}'?", default=False):
                self.dialogs.message(
                    "Plugin Disabled",
                    f"Plugin '{plugin_name}' has been disabled.\n\n"
                    "Note: Config system not yet implemented.\n"
                    "Plugin will remain active until restart.",
                )

        elif action == "enable":
            if self.dialogs.confirm(f"Enable plugin '{plugin_name}'?", default=True):
                self.dialogs.message(
                    "Plugin Enabled",
                    f"Plugin '{plugin_name}' has been enabled.\n\n"
                    "Plugin will be loaded on next restart.",
                )

        elif action == "configure":
            self.dialogs.message(
                "Configure Plugin",
                f"Configuration editor coming soon.\n\n"
                f"For now, edit manually:\n"
                f"~/.config/audiomason/plugins/{plugin_name}.yaml",
            )

        elif action == "info":
            plugin_dir = Path(__file__).parent.parent / plugin_name
            manifest_path = plugin_dir / "plugin.yaml"

            if manifest_path.exists():
                try:
                    import yaml

                    with open(manifest_path) as f:
                        manifest = yaml.safe_load(f)

                    info = f"Plugin: {manifest.get('name', plugin_name)}\n"
                    info += f"Version: {manifest.get('version', 'unknown')}\n"
                    info += f"Description: {manifest.get('description', 'N/A')}\n"
                    info += f"Author: {manifest.get('author', 'unknown')}\n"

                    self.dialogs.message("Plugin Info", info)
                except Exception as e:
                    self.dialogs.message("Error", f"Failed to read plugin info:\n{e}")
            else:
                self.dialogs.message("Error", f"Plugin manifest not found:\n{manifest_path}")

        if action == "delete" and self.dialogs.confirm(
            f"DELETE plugin '{plugin_name}'?\n\nThis cannot be undone!", default=False
        ):
            plugin_dir = Path(__file__).parent.parent / plugin_name
            try:
                import shutil

                shutil.rmtree(plugin_dir)
                self.dialogs.message(
                    "Plugin Deleted",
                    f"Plugin '{plugin_name}' has been removed.\n\n"
                    "Restart AudioMason to complete removal.",
                )
            except Exception as e:
                self.dialogs.message("Error", f"Failed to delete plugin:\n{e}")


class WebScreen:
    """Web server control screen."""

    def __init__(self, screen, theme: Theme, config: dict):
        """Initialize web screen."""
        self.screen = screen
        self.theme = theme
        self.config = config
        self.menu = Menu(screen, theme)
        self.dialogs = Dialogs(screen, theme)

    def show(self) -> str:
        """Show web server menu."""
        items = [
            MenuItem("1", "Start Web Server", "Start web interface on port 8080", "start", True),
            MenuItem("2", "Stop Web Server", "Stop running web server", "stop", True),
            MenuItem("0", "Back", "Return to main menu", "back", True),
        ]

        action = self.menu.show(
            title="Web Server",
            items=items,
            footer="<Select>                                             <Back>",
        )

        if action == "start":
            self.dialogs.message(
                "Web Server",
                "Exit TUI and run:\n\n  audiomason web\n\nThen open: http://localhost:8080",
            )
        elif action == "stop":
            self.dialogs.message(
                "Web Server",
                "To stop web server, press Ctrl+C in the terminal\nwhere it's running.",
            )

        return action


class DaemonScreen:
    """Daemon mode control screen."""

    def __init__(self, screen, theme: Theme, config: dict):
        """Initialize daemon screen."""
        self.screen = screen
        self.theme = theme
        self.config = config
        self.menu = Menu(screen, theme)
        self.dialogs = Dialogs(screen, theme)

    def show(self) -> str:
        """Show daemon menu."""
        items = [
            MenuItem("1", "Start Daemon", "Start background folder watcher", "start", True),
            MenuItem("2", "Stop Daemon", "Stop background watcher", "stop", True),
            MenuItem("3", "Configure", "Edit daemon settings", "config", True),
            MenuItem("0", "Back", "Return to main menu", "back", True),
        ]

        action = self.menu.show(
            title="Daemon Mode",
            items=items,
            footer="<Select>                                             <Back>",
        )

        if action == "start":
            self.dialogs.message(
                "Daemon Mode",
                "Exit TUI and run:\n\n  audiomason daemon\n\n"
                "It will run in the foreground.\n"
                "Press Ctrl+C to stop.",
            )
        elif action == "stop":
            self.dialogs.message(
                "Daemon Mode", "To stop daemon, press Ctrl+C in the terminal\nwhere it's running."
            )
        elif action == "config":
            return "back"

        return action


class LogsScreen:
    """Logs viewer screen."""

    def __init__(self, screen, theme: Theme, config: dict):
        """Initialize logs screen."""
        self.screen = screen
        self.theme = theme
        self.config = config
        self.menu = Menu(screen, theme)
        self.dialogs = Dialogs(screen, theme)

    def show(self) -> str:
        """Show logs menu."""
        log_dir = Path.home() / ".audiomason" / "logs"

        items = [
            MenuItem("1", "View Latest Log", "Show most recent log file", "latest", True),
            MenuItem("2", "View All Logs", "List all log files", "all", True),
            MenuItem("3", "Clear Logs", "Delete all log files", "clear", True),
            MenuItem("0", "Back", "Return to main menu", "back", True),
        ]

        action = self.menu.show(
            title="View Logs",
            items=items,
            footer="<Select>                                             <Back>",
        )

        if action == "latest":
            if log_dir.exists():
                log_files = sorted(
                    log_dir.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True
                )
                if log_files:
                    latest = log_files[0]
                    try:
                        content = latest.read_text()
                        lines = content.split("\n")[-20:]
                        self.dialogs.message(f"Latest Log: {latest.name}", "\n".join(lines))
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

        if action == "clear" and self.dialogs.confirm("Delete all log files?", default=False):
            if log_dir.exists():
                count = 0
                for log_file in log_dir.glob("*.log"):
                    log_file.unlink()
                    count += 1
                self.dialogs.message("Logs Cleared", f"Deleted {count} log file(s)")
            else:
                self.dialogs.message("No Logs", "No log files to delete")

        return action


class AboutScreen:
    """About screen."""

    def __init__(self, screen, theme: Theme, config: dict):
        """Initialize about screen."""
        self.screen = screen
        self.theme = theme
        self.config = config
        self.dialogs = Dialogs(screen, theme)

    def show(self) -> str:
        """Show about information."""
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


# ============================================================================
# TUI PLUGIN
# ============================================================================


class TUIPlugin:
    """Terminal user interface plugin."""

    def __init__(self, config: dict | None = None):
        """Initialize TUI plugin."""
        if not HAS_CURSES:
            raise ImportError("curses not available")

        self.config = config or {}
        self.logger = get_logger(__name__)

        # Handle verbosity - accept both enum and int
        if "verbosity" in self.config:
            verbosity = self.config["verbosity"]
            # Convert enum to int if needed
            if hasattr(verbosity, "value"):
                # It's an enum
                verbosity_int = verbosity.value
            elif isinstance(verbosity, int):
                # Already int
                verbosity_int = verbosity
            else:
                # String or other - try to convert
                verbosity_int = int(verbosity) if str(verbosity).isdigit() else 1

            set_verbosity(verbosity_int)
            self.config["verbosity"] = verbosity_int  # Store as int for later use

        self.screen: Any = None
        self.theme: Theme | None = None
        self.current_screen = "main"
        self.screen_stack: list[str] = []

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
        """Main TUI loop - FIX #8."""
        self.screen = stdscr

        # CRITICAL: Enable keypad mode for arrow keys
        self.screen.keypad(True)
        curses.curs_set(0)

        # Setup file logging for debug/verbose (stderr is blocked by curses)
        verbosity = self.config.get("verbosity", 1)
        if verbosity >= 2:  # VERBOSE or DEBUG
            from pathlib import Path

            from audiomason.core.logging import set_log_file

            log_file = Path.home() / ".audiomason" / "logs" / "tui.log"
            set_log_file(log_file)
            self.logger.verbose(f"TUI started with verbosity={verbosity}")

        self.theme = Theme(self.config)
        self.theme.init_colors()

        self.screen.clear()
        self.screen.refresh()

        while True:
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
                    elif action in ("wizard", "process", "wizards"):
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
                    wizards_screen = WizardsScreen(self.screen, self.theme, self.config)
                    action = wizards_screen.show()
                    if action == "back":
                        self.current_screen = (
                            self.screen_stack.pop() if self.screen_stack else "main"
                        )

                elif self.current_screen == "config":
                    config_screen = ConfigScreen(self.screen, self.theme, self.config)
                    action = config_screen.show()
                    if action == "back":
                        self.current_screen = (
                            self.screen_stack.pop() if self.screen_stack else "main"
                        )

                elif self.current_screen == "plugins":
                    plugins_screen = PluginsScreen(self.screen, self.theme, self.config)
                    action = plugins_screen.show()
                    if action == "back":
                        self.current_screen = (
                            self.screen_stack.pop() if self.screen_stack else "main"
                        )

                elif self.current_screen == "web":
                    web_screen = WebScreen(self.screen, self.theme, self.config)
                    action = web_screen.show()
                    if action == "back":
                        self.current_screen = (
                            self.screen_stack.pop() if self.screen_stack else "main"
                        )

                elif self.current_screen == "daemon":
                    daemon_screen = DaemonScreen(self.screen, self.theme, self.config)
                    action = daemon_screen.show()
                    if action == "back":
                        self.current_screen = (
                            self.screen_stack.pop() if self.screen_stack else "main"
                        )

                elif self.current_screen == "logs":
                    logs_screen = LogsScreen(self.screen, self.theme, self.config)
                    action = logs_screen.show()
                    if action == "back":
                        self.current_screen = (
                            self.screen_stack.pop() if self.screen_stack else "main"
                        )

                elif self.current_screen == "about":
                    about_screen = AboutScreen(self.screen, self.theme, self.config)
                    action = about_screen.show()
                    self.current_screen = self.screen_stack.pop() if self.screen_stack else "main"

                else:
                    self.current_screen = "main"

            except Exception as e:
                self.logger.error(f"Screen error: {e}")
                self.current_screen = "main"
                self.screen_stack.clear()
