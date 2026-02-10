"""TUI Plugin - ncurses Terminal User Interface for AudioMason2.

Provides full control over AudioMason features via text-based interface
styled after raspi-config.

Entry point: `audiomason tui`
"""

from __future__ import annotations

import curses
from pathlib import Path
from typing import Any

from audiomason.core.config_service import ConfigService
from audiomason.core.loader import PluginLoader
from audiomason.core.logging import get_logger
from audiomason.core.plugin_registry import PluginRegistry

from .menu_engine import MenuEngine, MenuItem

logger = get_logger(__name__)


class TUIPlugin:
    """TUI plugin implementing ICLICommands interface."""

    def __init__(self) -> None:
        """Initialize TUI plugin."""
        self._config_service: ConfigService | None = None
        self._plugin_registry: PluginRegistry | None = None
        self._plugin_loader: PluginLoader | None = None
        self._engine: MenuEngine | None = None

    def get_cli_commands(self) -> dict[str, Any]:
        """Return CLI command handlers (ICLICommands interface)."""
        return {
            "tui2": self._run_tui_command,
        }

    def _run_tui_command(self, argv: list[str]) -> str:
        """Entry point for `audiomason tui` command.

        Args:
            argv: Command line arguments

        Returns:
            Status message
        """
        _ = argv  # Reserved for future flags like --tui.start-at

        logger.info("Starting TUI...")

        try:
            # Initialize services
            self._init_services()

            # Run ncurses wrapper
            curses.wrapper(self._run_tui)

            logger.info("TUI exited normally")
            return "OK"

        except Exception as e:
            logger.error(f"TUI error: {e}")
            return f"ERROR: {e}"

    def _init_services(self) -> None:
        """Initialize core services."""
        self._config_service = ConfigService()
        self._plugin_registry = PluginRegistry(self._config_service)

        # Find plugins directory
        # Try relative to this file first (built-in), then standard locations
        plugin_file = Path(__file__).resolve()
        plugins_dir = plugin_file.parent.parent

        self._plugin_loader = PluginLoader(
            builtin_plugins_dir=plugins_dir,
            registry=self._plugin_registry,
        )

    def _run_tui(self, stdscr: Any) -> None:
        """Run TUI in curses wrapper.

        Args:
            stdscr: Curses standard screen
        """
        self._engine = MenuEngine(stdscr)

        # Build main menu
        main_menu = self._build_main_menu()
        self._engine.set_menu("Main Menu", main_menu)

        # Run menu loop
        self._engine.run()

    def _build_main_menu(self) -> list[MenuItem]:
        """Build main menu items.

        Returns:
            List of menu items
        """
        return [
            MenuItem(
                id="plugins",
                label="1. Plugins",
                submenu=self._build_plugins_menu(),
                description="Manage plugins",
            ),
            MenuItem(
                id="wizards",
                label="2. Wizards",
                action=lambda: "Not implemented yet",
                description="Run and manage wizards",
            ),
            MenuItem(
                id="config",
                label="3. Configuration",
                action=lambda: "Not implemented yet",
                description="Edit configuration",
            ),
            MenuItem(
                id="jobs",
                label="4. Jobs",
                action=lambda: "Not implemented yet",
                description="View and manage jobs",
            ),
            MenuItem(
                id="files",
                label="5. Files",
                action=lambda: "Not implemented yet",
                description="Browse files",
            ),
            MenuItem(
                id="logs",
                label="6. System Log",
                action=lambda: "Not implemented yet",
                description="View system log",
            ),
            MenuItem(
                id="exit",
                label="7. Exit",
                action=self._action_exit,
                description="Exit TUI",
            ),
        ]

    def _build_plugins_menu(self) -> list[MenuItem]:
        """Build plugins submenu.

        Returns:
            List of menu items
        """
        return [
            MenuItem(
                id="list_plugins",
                label="1. List Plugins",
                action=self._action_list_plugins,
                description="Show all plugins",
            ),
            MenuItem(
                id="toggle_plugin",
                label="2. Enable/Disable Plugin",
                action=self._action_toggle_plugin_menu,
                description="Toggle plugin state",
            ),
            MenuItem(
                id="back",
                label="3. Back to Main Menu",
                action=self._action_back,
                description="Return to main menu",
            ),
        ]

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

    def _action_list_plugins(self) -> str | None:
        """List all plugins action."""
        if not self._plugin_loader or not self._plugin_registry or not self._engine:
            return "Services not initialized"

        try:
            # Discover plugins
            plugin_dirs = self._plugin_loader.discover()

            if not plugin_dirs:
                return "No plugins found"

            # Build list of plugin info
            items: list[MenuItem] = []

            for plugin_dir in plugin_dirs:
                try:
                    manifest = self._plugin_loader.load_manifest_only(plugin_dir)
                    is_enabled = self._plugin_registry.is_enabled(manifest.name)

                    status = "[OK]" if is_enabled else "[--]"
                    label = f"{status} {manifest.name} v{manifest.version}"

                    items.append(
                        MenuItem(
                            id=manifest.name,
                            label=label,
                            enabled=is_enabled,
                            description=manifest.description,
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to load manifest from {plugin_dir}: {e}")
                    items.append(
                        MenuItem(
                            id=plugin_dir.name,
                            label=f"[??] {plugin_dir.name} (error)",
                            enabled=False,
                            description=str(e),
                        )
                    )

            # Add back option
            items.append(
                MenuItem(
                    id="back",
                    label="<< Back",
                    action=self._action_back,
                )
            )

            # Show as submenu
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
            # Discover plugins
            plugin_dirs = self._plugin_loader.discover()

            if not plugin_dirs:
                return "No plugins found"

            # Build toggle menu
            items: list[MenuItem] = []

            for plugin_dir in plugin_dirs:
                try:
                    manifest = self._plugin_loader.load_manifest_only(plugin_dir)
                    is_enabled = self._plugin_registry.is_enabled(manifest.name)

                    status = "[ON] " if is_enabled else "[OFF]"
                    label = f"{status} {manifest.name}"

                    # Create toggle action for this plugin
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
                            description=f"Toggle {manifest.name}",
                        )
                    )
                except Exception as e:
                    logger.warning(f"Failed to load manifest from {plugin_dir}: {e}")

            # Add back option
            items.append(
                MenuItem(
                    id="back",
                    label="<< Back",
                    action=self._action_back,
                )
            )

            # Show as submenu
            self._engine.push_menu("Toggle Plugin", items)
            return None

        except Exception as e:
            logger.error(f"Failed to build toggle menu: {e}")
            return f"Error: {e}"

    def _toggle_plugin(self, name: str, currently_enabled: bool) -> str | None:
        """Toggle plugin enabled state.

        Args:
            name: Plugin name
            currently_enabled: Current state

        Returns:
            Status message
        """
        if not self._plugin_registry or not self._engine:
            return "Services not initialized"

        try:
            new_state = not currently_enabled
            action = "Enable" if new_state else "Disable"

            # Confirm
            if self._engine.confirm_dialog(f"{action} plugin '{name}'?"):
                self._plugin_registry.set_enabled(name, new_state)
                logger.info(f"Plugin {name} {'enabled' if new_state else 'disabled'}")

                # Go back to refresh list
                self._engine.pop_menu()
                # Re-open toggle menu to show updated state
                self._action_toggle_plugin_menu()

                return f"Plugin {name} {'enabled' if new_state else 'disabled'}"
            else:
                return "Cancelled"

        except Exception as e:
            logger.error(f"Failed to toggle plugin {name}: {e}")
            return f"Error: {e}"
