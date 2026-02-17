"""TUI Plugin - ncurses Terminal User Interface for AudioMason2.

Provides full control over AudioMason features via text-based interface
styled after raspi-config.

Entry point: Called by CLI plugin via `audiomason tui`
"""

from __future__ import annotations

import contextlib
import os

# ruff: noqa: E501

# Fix ESC delay - must be set before importing curses
os.environ.setdefault("ESCDELAY", "25")

import curses
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from audiomason.core.config import ConfigResolver
from audiomason.core.config_service import ConfigService
from audiomason.core.loader import PluginLoader
from audiomason.core.logging import get_logger
from audiomason.core.orchestration import Orchestrator
from audiomason.core.plugin_registry import PluginRegistry
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)


# =============================================================================
# COLOR CONSTANTS
# =============================================================================

COLOR_NORMAL = 1
COLOR_CURSOR = 2
COLOR_BORDER = 3
COLOR_TITLE = 4
COLOR_HELP = 5
COLOR_ERROR = 6
COLOR_SUCCESS = 7


# =============================================================================
# MENU ENGINE
# =============================================================================


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
        """Initialize menu engine."""
        self.stdscr = stdscr
        self.selected_index = 0
        self.scroll_offset = 0  # For scrolling long lists
        self.menu_stack: list[
            tuple[str, list[MenuItem], int, int, str, dict[str, Callable[[], str | None]]]
        ] = []
        self.current_title = "Main Menu"
        self.current_items: list[MenuItem] = []
        self.help_text: str = ""  # Custom help text (empty = default)
        self.key_handlers: dict[str, Callable[[], str | None]] = {}  # Custom key handlers
        self.message: tuple[str, int] | None = None
        self.running = True

        self._init_colors()
        self._init_curses()

    def _init_colors(self) -> None:
        """Initialize ncurses color pairs for raspi-config style."""
        curses.start_color()
        curses.use_default_colors()

        curses.init_pair(COLOR_NORMAL, curses.COLOR_BLACK, curses.COLOR_WHITE)
        curses.init_pair(COLOR_CURSOR, curses.COLOR_WHITE, curses.COLOR_RED)
        curses.init_pair(COLOR_BORDER, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(COLOR_TITLE, curses.COLOR_WHITE, curses.COLOR_RED)
        curses.init_pair(COLOR_HELP, curses.COLOR_BLACK, curses.COLOR_WHITE)
        curses.init_pair(COLOR_ERROR, curses.COLOR_WHITE, curses.COLOR_RED)
        curses.init_pair(COLOR_SUCCESS, curses.COLOR_BLACK, curses.COLOR_GREEN)

    def _init_curses(self) -> None:
        """Initialize curses settings."""
        curses.curs_set(0)
        self.stdscr.keypad(True)
        self.stdscr.timeout(-1)

    def set_menu(
        self,
        title: str,
        items: list[MenuItem],
        help_text: str = "",
        key_handlers: dict[str, Callable[[], str | None]] | None = None,
    ) -> None:
        """Set current menu."""
        self.current_title = title
        self.current_items = items
        self.selected_index = 0
        self.scroll_offset = 0
        self.help_text = help_text
        self.key_handlers = key_handlers or {}

    def push_menu(
        self,
        title: str,
        items: list[MenuItem],
        help_text: str = "",
        key_handlers: dict[str, Callable[[], str | None]] | None = None,
    ) -> None:
        """Push new menu onto stack (enter submenu)."""
        self.menu_stack.append(
            (
                self.current_title,
                self.current_items,
                self.selected_index,
                self.scroll_offset,
                self.help_text,
                self.key_handlers,
            )
        )
        self.set_menu(title, items, help_text, key_handlers)

    def pop_menu(self) -> bool:
        """Pop menu from stack (go back)."""
        if not self.menu_stack:
            return False

        title, items, selected, scroll, help_text, key_handlers = self.menu_stack.pop()
        self.current_title = title
        self.current_items = items
        self.selected_index = selected
        self.scroll_offset = scroll
        self.help_text = help_text
        self.key_handlers = key_handlers
        return True

    def show_message(self, text: str, is_error: bool = False) -> None:
        """Show temporary message."""
        color = COLOR_ERROR if is_error else COLOR_SUCCESS
        self.message = (text, color)

    def clear_message(self) -> None:
        """Clear current message."""
        self.message = None

    def draw(self) -> None:
        """Draw the menu screen."""
        self.stdscr.clear()
        height, width = self.stdscr.getmaxyx()

        self.stdscr.bkgd(" ", curses.color_pair(COLOR_BORDER))

        # Calculate window dimensions
        win_width = min(70, width - 4)
        max_visible_items = min(20, height - 10)  # Max items visible at once
        visible_items = min(len(self.current_items), max_visible_items)
        win_height = visible_items + 6
        win_x = (width - win_width) // 2
        win_y = (height - win_height) // 2

        # Draw window background
        for y in range(win_y, win_y + win_height):
            self.stdscr.addstr(y, win_x, " " * win_width, curses.color_pair(COLOR_NORMAL))

        self._draw_border(win_y, win_x, win_height, win_width)

        # Draw title (truncated to fit)
        title = f" AudioMason v2 - {self.current_title} "
        max_title_len = win_width - 4
        if len(title) > max_title_len:
            title = title[: max_title_len - 3] + "..."
        title_x = win_x + (win_width - len(title)) // 2
        if title_x < win_x:
            title_x = win_x
        with contextlib.suppress(curses.error):
            self.stdscr.addstr(win_y, title_x, title, curses.color_pair(COLOR_TITLE))

        # Calculate scroll position
        if self.selected_index < self.scroll_offset:
            self.scroll_offset = self.selected_index
        elif self.selected_index >= self.scroll_offset + max_visible_items:
            self.scroll_offset = self.selected_index - max_visible_items + 1

        # Draw menu items with scrolling
        item_start_y = win_y + 2
        for display_idx in range(visible_items):
            item_idx = display_idx + self.scroll_offset
            if item_idx >= len(self.current_items):
                break

            item = self.current_items[item_idx]

            prefix = "[X] " if not item.enabled else "    "
            text = f"{prefix}{item.label}"
            text = text[: win_width - 4]
            text = text.ljust(win_width - 4)

            attr = (
                curses.color_pair(COLOR_CURSOR)
                if item_idx == self.selected_index
                else curses.color_pair(COLOR_NORMAL)
            )

            with contextlib.suppress(curses.error):
                self.stdscr.addstr(item_start_y + display_idx, win_x + 2, text, attr)

        # Draw scroll indicators
        if self.scroll_offset > 0:
            with contextlib.suppress(curses.error):
                self.stdscr.addstr(
                    item_start_y - 1, win_x + win_width - 4, " ^ ", curses.color_pair(COLOR_HELP)
                )
        if self.scroll_offset + max_visible_items < len(self.current_items):
            with contextlib.suppress(curses.error):
                self.stdscr.addstr(
                    item_start_y + visible_items,
                    win_x + win_width - 4,
                    " v ",
                    curses.color_pair(COLOR_HELP),
                )

        # Draw help bar - use custom help text if set
        help_y = win_y + win_height - 2
        help_text = (
            self.help_text
            if self.help_text
            else " Up/Down:Navigate  Enter:Select  Esc:Back  q:Quit "
        )
        help_text = help_text[: win_width - 2].center(win_width - 2)
        with contextlib.suppress(curses.error):
            self.stdscr.addstr(help_y, win_x + 1, help_text, curses.color_pair(COLOR_HELP))

        # Draw message if any
        if self.message:
            msg_text, msg_color = self.message
            msg_y = win_y + win_height + 1
            if msg_y < height - 1:
                msg_text = msg_text[:win_width].center(win_width)
                with contextlib.suppress(curses.error):
                    self.stdscr.addstr(msg_y, win_x, msg_text, curses.color_pair(msg_color))

        self.stdscr.refresh()

    def _draw_border(self, y: int, x: int, h: int, w: int) -> None:
        """Draw box border."""
        attr = curses.color_pair(COLOR_NORMAL)

        self.stdscr.addch(y, x, curses.ACS_ULCORNER, attr)
        self.stdscr.addch(y, x + w - 1, curses.ACS_URCORNER, attr)
        self.stdscr.addch(y + h - 1, x, curses.ACS_LLCORNER, attr)
        self.stdscr.addch(y + h - 1, x + w - 1, curses.ACS_LRCORNER, attr)

        for i in range(1, w - 1):
            self.stdscr.addch(y, x + i, curses.ACS_HLINE, attr)
            self.stdscr.addch(y + h - 1, x + i, curses.ACS_HLINE, attr)

        for i in range(1, h - 1):
            self.stdscr.addch(y + i, x, curses.ACS_VLINE, attr)
            self.stdscr.addch(y + i, x + w - 1, curses.ACS_VLINE, attr)

        self.stdscr.addch(y + 1, x, curses.ACS_LTEE, attr)
        self.stdscr.addch(y + 1, x + w - 1, curses.ACS_RTEE, attr)
        for i in range(1, w - 1):
            self.stdscr.addch(y + 1, x + i, curses.ACS_HLINE, attr)

    def handle_input(self) -> bool:
        """Handle user input."""
        key = self.stdscr.getch()

        self.clear_message()

        if key in (curses.KEY_UP, ord("k")):
            if self.selected_index > 0:
                self.selected_index -= 1
            return True

        elif key in (curses.KEY_DOWN, ord("j")):
            if self.selected_index < len(self.current_items) - 1:
                self.selected_index += 1
            return True

        elif key in (curses.KEY_ENTER, ord("\n"), ord(" ")):
            if self.current_items:
                item = self.current_items[self.selected_index]
                if item.submenu is not None:
                    self.push_menu(item.label, item.submenu)
                elif item.action is not None:
                    result = item.action()
                    if result:
                        self.show_message(result)
            return True

        elif key in (27, ord("q")):
            if not self.pop_menu():
                self.running = False
            return True

        # Check custom key handlers
        if self.key_handlers:
            key_char = chr(key) if 32 <= key < 127 else ""
            if key_char in self.key_handlers:
                handler = self.key_handlers[key_char]
                result = handler()
                if result:
                    self.show_message(result)
                return True

        return True

    def run(self) -> None:
        """Run menu loop."""
        while self.running:
            self.draw()
            if not self.handle_input():
                break

    def confirm_dialog(self, message: str) -> bool:
        """Show yes/no confirmation dialog."""
        height, width = self.stdscr.getmaxyx()

        dialog_width = min(50, width - 4)
        dialog_height = 5
        dialog_x = (width - dialog_width) // 2
        dialog_y = (height - dialog_height) // 2

        for y in range(dialog_y, dialog_y + dialog_height):
            self.stdscr.addstr(y, dialog_x, " " * dialog_width, curses.color_pair(COLOR_NORMAL))

        self._draw_border(dialog_y, dialog_x, dialog_height, dialog_width)

        msg = message[: dialog_width - 4]
        self.stdscr.addstr(
            dialog_y + 1,
            dialog_x + 2,
            msg.center(dialog_width - 4),
            curses.color_pair(COLOR_NORMAL),
        )

        options = "[Y]es  [N]o"
        self.stdscr.addstr(
            dialog_y + 3,
            dialog_x + 2,
            options.center(dialog_width - 4),
            curses.color_pair(COLOR_HELP),
        )

        self.stdscr.refresh()

        while True:
            key = self.stdscr.getch()
            if key in (ord("y"), ord("Y")):
                return True
            elif key in (ord("n"), ord("N"), 27):
                return False

    def input_dialog(self, prompt: str, default: str = "") -> str | None:
        """Show text input dialog. Returns None if cancelled."""
        height, width = self.stdscr.getmaxyx()

        dialog_width = min(60, width - 4)
        dialog_height = 6
        dialog_x = (width - dialog_width) // 2
        dialog_y = (height - dialog_height) // 2

        # Draw dialog background
        for y in range(dialog_y, dialog_y + dialog_height):
            self.stdscr.addstr(y, dialog_x, " " * dialog_width, curses.color_pair(COLOR_NORMAL))

        self._draw_border(dialog_y, dialog_x, dialog_height, dialog_width)

        # Prompt
        msg = prompt[: dialog_width - 4]
        self.stdscr.addstr(
            dialog_y + 1,
            dialog_x + 2,
            msg,
            curses.color_pair(COLOR_NORMAL),
        )

        # Input field
        input_width = dialog_width - 6
        value = default

        # Help text
        help_text = "Enter: OK  Esc: Cancel"
        self.stdscr.addstr(
            dialog_y + 4,
            dialog_x + 2,
            help_text.center(dialog_width - 4),
            curses.color_pair(COLOR_HELP),
        )

        curses.curs_set(1)  # Show cursor

        while True:
            # Draw input field
            display_value = value[-input_width:] if len(value) > input_width else value
            field = display_value.ljust(input_width)
            self.stdscr.addstr(
                dialog_y + 2,
                dialog_x + 3,
                field,
                curses.color_pair(COLOR_CURSOR),
            )
            self.stdscr.move(dialog_y + 2, dialog_x + 3 + len(display_value))
            self.stdscr.refresh()

            key = self.stdscr.getch()

            if key in (curses.KEY_ENTER, ord("\n")):
                curses.curs_set(0)
                return value
            elif key == 27:  # Escape
                curses.curs_set(0)
                return None
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                if value:
                    value = value[:-1]
            elif 32 <= key <= 126:  # Printable ASCII
                value += chr(key)

        curses.curs_set(0)
        return None


# =============================================================================
# TUI PLUGIN
# =============================================================================


class TUIPlugin:
    """TUI plugin called by CLI."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize TUI plugin."""
        self._config = config or {}
        self._verbosity = self._config.get("verbosity", 1)

        self._config_service: ConfigService | None = None
        self._plugin_registry: PluginRegistry | None = None
        self._plugin_loader: PluginLoader | None = None
        self._orchestrator: Orchestrator | None = None
        self._file_service: FileService | None = None
        self._engine: MenuEngine | None = None

    async def run(self) -> None:
        """Run TUI (called by CLI plugin)."""
        logger.info("Starting TUI...")

        try:
            self._init_services()
            curses.wrapper(self._run_tui)
            logger.info("TUI exited normally")

        except Exception as e:
            logger.error(f"TUI error: {e}")
            raise

    def _init_services(self) -> None:
        """Initialize core services."""
        self._config_service = ConfigService()
        self._plugin_registry = PluginRegistry(self._config_service)
        self._orchestrator = Orchestrator()

        # Initialize FileService
        resolver = ConfigResolver()
        self._file_service = FileService.from_resolver(resolver)

        plugin_file = Path(__file__).resolve()
        plugins_dir = plugin_file.parent.parent

        self._plugin_loader = PluginLoader(
            builtin_plugins_dir=plugins_dir,
            registry=self._plugin_registry,
        )

    def _run_tui(self, stdscr: Any) -> None:
        """Run TUI in curses wrapper."""
        self._engine = MenuEngine(stdscr)
        main_menu = self._build_main_menu()
        self._engine.set_menu("Main Menu", main_menu)
        self._engine.run()

    def _build_main_menu(self) -> list[MenuItem]:
        """Build main menu items."""
        return [
            MenuItem(
                id="plugins",
                label="1. Plugins",
                submenu=self._build_plugins_menu(),
                description="Manage plugins",
            ),
            MenuItem(
                id="config",
                label="2. Configuration",
                submenu=self._build_config_menu(),
                description="View configuration",
            ),
            MenuItem(
                id="jobs",
                label="3. Jobs",
                submenu=self._build_jobs_menu(),
                description="View and manage jobs",
            ),
            MenuItem(
                id="files",
                label="4. Files",
                submenu=self._build_files_menu(),
                description="Browse files",
            ),
            MenuItem(
                id="logs",
                label="5. System Log",
                submenu=self._build_logs_menu(),
                description="View system log",
            ),
            MenuItem(
                id="exit",
                label="6. Exit",
                action=self._action_exit,
                description="Exit TUI",
            ),
        ]

    # =========================================================================
    # PLUGINS
    # =========================================================================

    def _build_plugins_menu(self) -> list[MenuItem]:
        """Build plugins submenu."""
        return [
            MenuItem(
                id="list_plugins",
                label="1. List Plugins",
                action=self._action_list_plugins,
            ),
            MenuItem(
                id="toggle_plugin",
                label="2. Enable/Disable Plugin",
                action=self._action_toggle_plugin_menu,
            ),
            MenuItem(
                id="configure_plugin",
                label="3. Configure Plugin",
                action=self._action_configure_plugin_menu,
            ),
            MenuItem(
                id="delete_plugin",
                label="4. Delete Plugin",
                action=self._action_delete_plugin_menu,
            ),
            MenuItem(
                id="back",
                label="5. Back to Main Menu",
                action=self._action_back,
            ),
        ]

    def _action_list_plugins(self) -> str | None:
        """List all plugins action."""
        if not self._plugin_loader or not self._plugin_registry or not self._engine:
            return "Services not initialized"

        try:
            plugin_dirs = self._plugin_loader.discover()

            if not plugin_dirs:
                return "No plugins found"

            items: list[MenuItem] = []

            for plugin_dir in plugin_dirs:
                try:
                    manifest = self._plugin_loader.load_manifest_only(plugin_dir)
                    is_enabled = self._plugin_registry.is_enabled(manifest.name)

                    status = "[OK]" if is_enabled else "[--]"
                    label = f"{status} {manifest.name} v{manifest.version}"

                    items.append(MenuItem(id=manifest.name, label=label, enabled=is_enabled))
                except Exception as e:
                    logger.warning(f"Failed to load manifest from {plugin_dir}: {e}")
                    items.append(
                        MenuItem(
                            id=plugin_dir.name,
                            label=f"[??] {plugin_dir.name} (error)",
                            enabled=False,
                        )
                    )

            items.append(MenuItem(id="back", label="<< Back", action=self._action_back))
            self._engine.push_menu("Plugins List", items)
            return None

        except Exception as e:
            logger.error(f"Failed to list plugins: {e}")
            return f"Error: {e}"

    def _action_toggle_plugin_menu(self) -> str | None:
        """Show toggle plugin menu."""
        if not self._plugin_loader or not self._plugin_registry or not self._engine:
            return "Services not initialized"

        try:
            plugin_dirs = self._plugin_loader.discover()

            if not plugin_dirs:
                return "No plugins found"

            items: list[MenuItem] = []

            for plugin_dir in plugin_dirs:
                try:
                    manifest = self._plugin_loader.load_manifest_only(plugin_dir)
                    is_enabled = self._plugin_registry.is_enabled(manifest.name)

                    status = "[ON] " if is_enabled else "[OFF]"
                    label = f"{status} {manifest.name}"
                    plugin_name = manifest.name

                    def make_toggle(name: str, enabled: bool) -> Any:
                        def toggle() -> str | None:
                            return self._toggle_plugin(name, enabled)

                        return toggle

                    items.append(
                        MenuItem(
                            id=manifest.name,
                            label=label,
                            action=make_toggle(plugin_name, is_enabled),
                            enabled=is_enabled,
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to load manifest from {plugin_dir}: {e}")

            items.append(MenuItem(id="back", label="<< Back", action=self._action_back))
            self._engine.push_menu("Toggle Plugin", items)
            return None

        except Exception as e:
            logger.error(f"Failed to build toggle menu: {e}")
            return f"Error: {e}"

    def _toggle_plugin(self, name: str, currently_enabled: bool) -> str | None:
        """Toggle plugin enabled state."""
        if not self._plugin_registry or not self._engine:
            return "Services not initialized"

        try:
            new_state = not currently_enabled
            action = "Enable" if new_state else "Disable"

            if self._engine.confirm_dialog(f"{action} plugin '{name}'?"):
                self._plugin_registry.set_enabled(name, new_state)
                logger.info(f"Plugin {name} {'enabled' if new_state else 'disabled'}")
                self._engine.pop_menu()
                self._action_toggle_plugin_menu()
                return f"Plugin {name} {'enabled' if new_state else 'disabled'}"
            else:
                return "Cancelled"

        except Exception as e:
            logger.error(f"Failed to toggle plugin {name}: {e}")
            return f"Error: {e}"

    def _action_configure_plugin_menu(self) -> str | None:
        """Show configure plugin menu."""
        if not self._plugin_loader or not self._engine:
            return "Services not initialized"

        try:
            plugin_dirs = self._plugin_loader.discover()

            if not plugin_dirs:
                return "No plugins found"

            items: list[MenuItem] = []

            for plugin_dir in plugin_dirs:
                try:
                    manifest = self._plugin_loader.load_manifest_only(plugin_dir)
                    plugin_name = manifest.name

                    def make_configure(name: str) -> Any:
                        def configure() -> str | None:
                            return self._configure_plugin(name)

                        return configure

                    items.append(
                        MenuItem(
                            id=manifest.name,
                            label=manifest.name,
                            action=make_configure(plugin_name),
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to load manifest from {plugin_dir}: {e}")

            items.append(MenuItem(id="back", label="<< Back", action=self._action_back))
            self._engine.push_menu("Configure Plugin", items)
            return None

        except Exception as e:
            logger.error(f"Failed to build configure menu: {e}")
            return f"Error: {e}"

    def _configure_plugin(self, name: str) -> str | None:
        """Configure a plugin (show config keys)."""
        if not self._config_service or not self._engine:
            return "Services not initialized"

        # Plugin config is under plugins.<name>.* namespace
        config_prefix = f"plugins.{name}."

        try:
            items_data = self._config_service.get_effective_items()

            items: list[MenuItem] = []
            found_any = False

            for item in items_data:
                if item.key.startswith(config_prefix):
                    found_any = True
                    value_str = str(item.value)
                    if len(value_str) > 20:
                        value_str = value_str[:17] + "..."

                    # Show just the key part after prefix
                    short_key = item.key[len(config_prefix) :]
                    label = f"{short_key} = {value_str}"

                    key = item.key
                    current_value = str(item.value)

                    def make_edit(k: str, v: str) -> Any:
                        def edit() -> str | None:
                            return self._edit_config_value(k, v)

                        return edit

                    items.append(
                        MenuItem(id=item.key, label=label, action=make_edit(key, current_value))
                    )

            if not found_any:
                return f"No config keys for plugin '{name}'"

            items.append(MenuItem(id="back", label="<< Back", action=self._action_back))
            self._engine.push_menu(f"Config: {name}", items)
            return None

        except Exception as e:
            logger.error(f"Failed to configure plugin {name}: {e}")
            return f"Error: {e}"

    def _action_delete_plugin_menu(self) -> str | None:
        """Show delete plugin menu (user plugins only)."""
        if not self._engine:
            return "Services not initialized"

        # Note: Deleting plugins is risky and spec says user plugins only
        # For now, show info message
        return "Plugin deletion not available (use file manager)"

    # =========================================================================
    # WIZARDS
    # =========================================================================

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    def _build_config_menu(self) -> list[MenuItem]:
        """Build configuration submenu."""
        return [
            MenuItem(id="view_config", label="1. View All Config", action=self._action_view_config),
            MenuItem(
                id="edit_config", label="2. Edit Config Value", action=self._action_edit_config_menu
            ),
            MenuItem(
                id="reset_config",
                label="3. Reset Key to Default",
                action=self._action_reset_config_menu,
            ),
            MenuItem(id="back", label="4. Back to Main Menu", action=self._action_back),
        ]

    def _action_view_config(self) -> str | None:
        """View all effective configuration."""
        if not self._config_service or not self._engine:
            return "Services not initialized"

        try:
            items_data = self._config_service.get_effective_items()

            if not items_data:
                return "No configuration found"

            items: list[MenuItem] = []

            for item in items_data:
                value_str = str(item.value)
                if len(value_str) > 30:
                    value_str = value_str[:27] + "..."
                label = f"{item.key} = {value_str}"

                key = item.key
                current_value = str(item.value)

                def make_edit(k: str, v: str) -> Any:
                    def edit() -> str | None:
                        return self._edit_config_value(k, v)

                    return edit

                items.append(
                    MenuItem(
                        id=item.key,
                        label=label,
                        action=make_edit(key, current_value),
                        description=f"Source: {item.source}",
                    )
                )

            items.append(MenuItem(id="back", label="<< Back", action=self._action_back))
            self._engine.push_menu("Configuration (Enter to edit)", items)
            return None

        except Exception as e:
            logger.error(f"Failed to view config: {e}")
            return f"Error: {e}"

    def _action_edit_config_menu(self) -> str | None:
        """Show edit config menu."""
        if not self._config_service or not self._engine:
            return "Services not initialized"

        try:
            items_data = self._config_service.get_effective_items()

            if not items_data:
                return "No configuration found"

            items: list[MenuItem] = []

            for item in items_data:
                value_str = str(item.value)
                if len(value_str) > 20:
                    value_str = value_str[:17] + "..."

                label = f"{item.key} = {value_str}"
                key = item.key
                current_value = str(item.value)

                def make_edit(k: str, v: str) -> Any:
                    def edit() -> str | None:
                        return self._edit_config_value(k, v)

                    return edit

                items.append(
                    MenuItem(id=item.key, label=label, action=make_edit(key, current_value))
                )

            items.append(MenuItem(id="back", label="<< Back", action=self._action_back))
            self._engine.push_menu("Edit Config", items)
            return None

        except Exception as e:
            logger.error(f"Failed to build edit config menu: {e}")
            return f"Error: {e}"

    def _edit_config_value(self, key: str, current_value: str) -> str | None:
        """Edit a config value."""
        if not self._config_service or not self._engine:
            return "Services not initialized"

        try:
            new_value = self._engine.input_dialog(f"Edit {key}:", current_value)

            if new_value is None:
                return "Cancelled"

            if new_value == current_value:
                return "No change"

            self._config_service.set_value(key, new_value)
            logger.info(f"Config {key} set to: {new_value}")

            # Refresh menu
            self._engine.pop_menu()
            self._action_edit_config_menu()

            return f"Set {key} = {new_value}"

        except Exception as e:
            logger.error(f"Failed to set config {key}: {e}")
            return f"Error: {e}"

    def _action_reset_config_menu(self) -> str | None:
        """Show reset config menu."""
        if not self._config_service or not self._engine:
            return "Services not initialized"

        try:
            items_data = self._config_service.get_effective_items()

            # Only show items from user_config (can be reset)
            user_items = [item for item in items_data if item.source == "user_config"]

            if not user_items:
                return "No user config keys to reset"

            items: list[MenuItem] = []

            for item in user_items:
                value_str = str(item.value)
                if len(value_str) > 20:
                    value_str = value_str[:17] + "..."

                label = f"{item.key} = {value_str}"
                key = item.key

                def make_reset(k: str) -> Any:
                    def reset() -> str | None:
                        return self._reset_config_value(k)

                    return reset

                items.append(MenuItem(id=item.key, label=label, action=make_reset(key)))

            items.append(MenuItem(id="back", label="<< Back", action=self._action_back))
            self._engine.push_menu("Reset Config Key", items)
            return None

        except Exception as e:
            logger.error(f"Failed to build reset config menu: {e}")
            return f"Error: {e}"

    def _reset_config_value(self, key: str) -> str | None:
        """Reset a config value to default."""
        if not self._config_service or not self._engine:
            return "Services not initialized"

        try:
            if not self._engine.confirm_dialog(f"Reset '{key}' to default?"):
                return "Cancelled"

            self._config_service.unset_value(key)
            logger.info(f"Reset config key: {key}")

            # Refresh menu
            self._engine.pop_menu()
            self._action_reset_config_menu()

            return f"Reset: {key}"

        except Exception as e:
            logger.error(f"Failed to reset config {key}: {e}")
            return f"Error: {e}"

    # =========================================================================
    # JOBS
    # =========================================================================

    def _build_jobs_menu(self) -> list[MenuItem]:
        """Build jobs submenu."""
        return [
            MenuItem(
                id="view_job_logs",
                label="1. View Job Logs",
                action=self._action_view_job_logs,
            ),
            MenuItem(id="back", label="2. Back to Main Menu", action=self._action_back),
        ]

    # =========================================================================
    # FILES
    # =========================================================================

    def _build_files_menu(self) -> list[MenuItem]:
        """Build files submenu."""
        return [
            MenuItem(id="browse_inbox", label="1. Browse Inbox", action=self._action_browse_inbox),
            MenuItem(id="browse_stage", label="2. Browse Stage", action=self._action_browse_stage),
            MenuItem(
                id="browse_outbox", label="3. Browse Outbox", action=self._action_browse_outbox
            ),
            MenuItem(id="back", label="4. Back to Main Menu", action=self._action_back),
        ]

    def _action_browse_inbox(self) -> str | None:
        """Browse inbox directory."""
        return self._browse_root(RootName.INBOX, "Inbox", ".")

    def _action_browse_stage(self) -> str | None:
        """Browse stage directory."""
        return self._browse_root(RootName.STAGE, "Stage", ".")

    def _action_browse_outbox(self) -> str | None:
        """Browse outbox directory."""
        return self._browse_root(RootName.OUTBOX, "Outbox", ".")

    def _browse_root(self, root: RootName, title: str, rel_path: str) -> str | None:
        """Browse a file root directory."""
        if not self._file_service or not self._engine:
            return "Services not initialized"

        try:
            entries = self._file_service.list_dir(root, rel_path, recursive=False)

            items: list[MenuItem] = []
            # Store entry info for key handlers
            entry_map: dict[str, tuple[str, bool]] = {}  # id -> (full_path, is_dir)

            # Add parent directory if not at root
            if rel_path != ".":
                parent_path = str(Path(rel_path).parent)
                if parent_path == ".":
                    parent_path = "."

                def make_navigate_parent(r: RootName, t: str, p: str) -> Any:
                    def nav() -> str | None:
                        return self._browse_root(r, t, p)

                    return nav

                items.append(
                    MenuItem(
                        id="..",
                        label="[DIR] ..",
                        action=make_navigate_parent(root, title, parent_path),
                    )
                )
                entry_map[".."] = (parent_path, True)

            # Sort: directories first, then by name
            sorted_entries = sorted(entries, key=lambda e: (not e.is_dir, e.rel_path))

            for entry in sorted_entries:
                entry_name = Path(entry.rel_path).name
                full_path = entry.rel_path

                if entry.is_dir:
                    prefix = "[DIR] "
                    display_name = entry_name[:47] + "..." if len(entry_name) > 50 else entry_name

                    # Enter navigates directly into directory
                    def make_navigate(r: RootName, t: str, p: str) -> Any:
                        def nav() -> str | None:
                            return self._browse_root(r, t, p)

                        return nav

                    items.append(
                        MenuItem(
                            id=entry.rel_path,
                            label=f"{prefix}{display_name}",
                            action=make_navigate(root, title, full_path),
                        )
                    )
                    entry_map[entry.rel_path] = (full_path, True)
                else:
                    prefix = "      "
                    size_str = (
                        f" ({self._format_size(entry.size)})" if entry.size is not None else ""
                    )
                    max_name_len = 50 - len(size_str)
                    display_name = (
                        entry_name[: max_name_len - 3] + "..."
                        if len(entry_name) > max_name_len
                        else entry_name
                    )

                    # Files have no default action (use shortcuts)
                    items.append(
                        MenuItem(
                            id=entry.rel_path,
                            label=f"{prefix}{display_name}{size_str}",
                        )
                    )
                    entry_map[entry.rel_path] = (full_path, False)

            if not entries and rel_path == ".":
                items.append(MenuItem(id="empty", label="(empty)"))

            items.append(MenuItem(id="back", label="<< Back", action=self._action_back))

            # Create key handlers for file operations
            def get_selected_entry() -> tuple[str, bool] | None:
                """Get currently selected entry path and is_dir."""
                if not self._engine or not self._engine.current_items:
                    return None
                idx = self._engine.selected_index
                if idx >= len(self._engine.current_items):
                    return None
                item_id = self._engine.current_items[idx].id
                return entry_map.get(item_id)

            def make_copy_handler(r: RootName) -> Callable[[], str | None]:
                def handler() -> str | None:
                    entry = get_selected_entry()
                    if not entry:
                        return "No item selected"
                    path, _ = entry
                    return self._copy_item(r, path)

                return handler

            def make_move_handler(r: RootName) -> Callable[[], str | None]:
                def handler() -> str | None:
                    entry = get_selected_entry()
                    if not entry:
                        return "No item selected"
                    path, _ = entry
                    return self._move_item(r, path)

                return handler

                return handler

            def make_delete_handler(r: RootName) -> Callable[[], str | None]:
                def handler() -> str | None:
                    entry = get_selected_entry()
                    if not entry:
                        return "No item selected"
                    path, is_dir = entry
                    return self._delete_item(r, path, is_dir)

                return handler

            key_handlers: dict[str, Callable[[], str | None]] = {
                "c": make_copy_handler(root),
                "m": make_move_handler(root),
                "d": make_delete_handler(root),
            }

            # Truncate display path for title
            display_path = rel_path if rel_path != "." else "/"
            if len(display_path) > 30:
                display_path = "..." + display_path[-27:]

            help_text = " c:Copy  m:Move  d:Delete  Esc:Back "
            self._engine.push_menu(f"{title}: {display_path}", items, help_text, key_handlers)
            return None

        except Exception as e:
            logger.error(f"Failed to browse {root}: {e}")
            return f"Error: {e}"

    def _copy_item(self, root: RootName, rel_path: str) -> str | None:
        """Copy file/directory within same root."""
        if not self._file_service or not self._engine:
            return "Services not initialized"

        try:
            filename = Path(rel_path).name

            # Ask for new name
            new_name = self._engine.input_dialog("Copy as (new name):", filename + "_copy")
            if not new_name:
                return "Cancelled"

            # Calculate new path
            parent = str(Path(rel_path).parent)
            new_path = new_name if parent == "." else f"{parent}/{new_name}"

            self._file_service.copy(root, rel_path, new_path)
            logger.info(f"Copied {root}/{rel_path} to {new_path}")

            return f"Copied as: {new_name}"

        except Exception as e:
            logger.error(f"Failed to copy: {e}")
            return f"Error: {e}"

    def _move_item(self, root: RootName, rel_path: str) -> str | None:
        """Move/rename file/directory within same root."""
        if not self._file_service or not self._engine:
            return "Services not initialized"

        try:
            filename = Path(rel_path).name

            # Ask for new name
            new_name = self._engine.input_dialog("Move/rename to:", filename)
            if not new_name or new_name == filename:
                return "Cancelled"

            # Calculate new path
            parent = str(Path(rel_path).parent)
            new_path = new_name if parent == "." else f"{parent}/{new_name}"

            self._file_service.rename(root, rel_path, new_path)
            logger.info(f"Renamed {root}/{rel_path} to {new_path}")

            # Refresh - pop and re-browse
            if self._engine.pop_menu():
                # Get current title to extract root name
                return f"Renamed to: {new_name}"

            return f"Renamed to: {new_name}"

        except Exception as e:
            logger.error(f"Failed to move/rename: {e}")
            return f"Error: {e}"

    def _delete_item(self, root: RootName, rel_path: str, is_dir: bool) -> str | None:
        """Delete a file or directory."""
        if not self._file_service or not self._engine:
            return "Services not initialized"

        try:
            filename = Path(rel_path).name
            item_type = "directory" if is_dir else "file"

            if not self._engine.confirm_dialog(f"Delete {item_type} '{filename}'?"):
                return "Cancelled"

            if is_dir:
                self._file_service.rmtree(root, rel_path)
            else:
                self._file_service.delete_file(root, rel_path)

            logger.info(f"Deleted {root}/{rel_path}")

            # Refresh current directory by popping and letting parent re-display
            self._engine.pop_menu()

            return f"Deleted: {filename}"

        except Exception as e:
            logger.error(f"Failed to delete {rel_path}: {e}")
            return f"Error: {e}"

    def _format_size(self, size: int) -> str:
        """Format file size in human readable form."""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size // 1024} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size // (1024 * 1024)} MB"
        else:
            return f"{size // (1024 * 1024 * 1024)} GB"

    # =========================================================================
    # SYSTEM LOG
    # =========================================================================

    def _build_logs_menu(self) -> list[MenuItem]:
        """Build logs submenu."""
        return [
            MenuItem(
                id="view_system_log",
                label="1. View System Log",
                action=self._action_view_system_log,
            ),
            MenuItem(
                id="view_job_logs", label="2. View Job Logs", action=self._action_view_job_logs
            ),
            MenuItem(id="back", label="3. Back to Main Menu", action=self._action_back),
        ]

    def _action_view_system_log(self) -> str | None:
        """View system log file."""
        if not self._engine:
            return "Services not initialized"

        try:
            # Get log path from env or default
            log_path = os.environ.get(
                "AUDIOMASON_TUI_SYSTEM_LOG_PATH",
                str(Path.home() / ".audiomason/logs/audiomason.log"),
            )

            log_file = Path(log_path)

            if not log_file.exists():
                return f"Log file not found: {log_path}"

            # Read last 200 lines
            try:
                with open(log_file, encoding="utf-8", errors="replace") as f:
                    all_lines = f.readlines()
                    lines = all_lines[-200:]
            except Exception as e:
                return f"Failed to read log: {e}"

            if not lines:
                return "Log is empty"

            items: list[MenuItem] = []

            for i, line in enumerate(lines[-30:]):  # Show last 30 in menu
                line = line.strip()
                if len(line) > 55:
                    line = line[:52] + "..."
                items.append(MenuItem(id=f"line_{i}", label=line))

            items.append(MenuItem(id="back", label="<< Back", action=self._action_back))
            self._engine.push_menu("System Log (last 30 lines)", items)
            return None

        except Exception as e:
            logger.error(f"Failed to view system log: {e}")
            return f"Error: {e}"

    def _action_view_job_logs(self) -> str | None:
        """View logs for completed jobs."""
        if not self._orchestrator or not self._engine:
            return "Services not initialized"

        try:
            jobs = self._orchestrator.list_jobs()

            if not jobs:
                return "No jobs found"

            items: list[MenuItem] = []

            for job in jobs:
                state_str = job.state.name[:4] if job.state else "????"
                type_str = job.type.name if job.type else "?"
                label = f"[{state_str}] {job.job_id[:8]}... ({type_str})"
                job_id = job.job_id

                def make_view_log(jid: str) -> Any:
                    def view() -> str | None:
                        return self._view_job_log(jid)

                    return view

                items.append(MenuItem(id=job.job_id, label=label, action=make_view_log(job_id)))

            items.append(MenuItem(id="back", label="<< Back", action=self._action_back))
            self._engine.push_menu("Job Logs", items)
            return None

        except Exception as e:
            logger.error(f"Failed to list job logs: {e}")
            return f"Error: {e}"

    def _view_job_log(self, job_id: str) -> str | None:
        """View log for a specific job."""
        if not self._orchestrator or not self._engine:
            return "Services not initialized"

        try:
            log_text, _offset = self._orchestrator.read_log(job_id, offset=0, limit_bytes=4096)

            if not log_text:
                return "Log is empty"

            # Split into lines and show as menu items
            lines = log_text.strip().split("\n")
            items: list[MenuItem] = []

            for i, line in enumerate(lines[-20:]):  # Last 20 lines
                # Truncate long lines
                if len(line) > 50:
                    line = line[:47] + "..."
                items.append(MenuItem(id=f"line_{i}", label=line))

            items.append(MenuItem(id="back", label="<< Back", action=self._action_back))
            self._engine.push_menu(f"Log: {job_id[:8]}...", items)
            return None

        except Exception as e:
            logger.error(f"Failed to read log for job {job_id}: {e}")
            return f"Error: {e}"

    # =========================================================================
    # COMMON ACTIONS
    # =========================================================================

    def _action_exit(self) -> str | None:
        """Exit TUI action."""
        if self._engine:
            self._engine.running = False
        return None

    def _action_back(self) -> str | None:
        """Go back action."""
        if self._engine:
            self._engine.pop_menu()
        return None
