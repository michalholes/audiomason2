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
from audiomason.core.orchestration import Orchestrator
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
        self._orchestrator: Orchestrator | None = None
        self._engine: MenuEngine | None = None

    def get_cli_commands(self) -> dict[str, Any]:
        """Return CLI command handlers (ICLICommands interface)."""
        return {
            "tui": self._run_tui_command,
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
        self._orchestrator = Orchestrator()

        # Find plugins directory
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
        """Build main menu items."""
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
                submenu=self._build_wizards_menu(),
                description="Run and manage wizards",
            ),
            MenuItem(
                id="config",
                label="3. Configuration",
                submenu=self._build_config_menu(),
                description="View configuration",
            ),
            MenuItem(
                id="jobs",
                label="4. Jobs",
                submenu=self._build_jobs_menu(),
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
                            description=f"Toggle {manifest.name}",
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

    # =========================================================================
    # WIZARDS
    # =========================================================================

    def _build_wizards_menu(self) -> list[MenuItem]:
        """Build wizards submenu."""
        return [
            MenuItem(
                id="list_wizards",
                label="1. List Wizards",
                action=self._action_list_wizards,
                description="Show available wizards",
            ),
            MenuItem(
                id="back",
                label="2. Back to Main Menu",
                action=self._action_back,
                description="Return to main menu",
            ),
        ]

    def _action_list_wizards(self) -> str | None:
        """List all wizards."""
        if not self._engine:
            return "Services not initialized"

        try:
            # Import here to avoid circular imports
            from audiomason.core.wizard_service import WizardService

            svc = WizardService()
            wizards = svc.list_wizards()

            if not wizards:
                return "No wizards found"

            items: list[MenuItem] = []

            for w in wizards:
                items.append(
                    MenuItem(
                        id=w.name,
                        label=w.name,
                        description=f"Wizard: {w.name}",
                    )
                )

            items.append(MenuItem(id="back", label="<< Back", action=self._action_back))

            self._engine.push_menu("Wizards List", items)
            return None

        except Exception as e:
            logger.error(f"Failed to list wizards: {e}")
            return f"Error: {e}"

    # =========================================================================
    # JOBS
    # =========================================================================

    def _build_jobs_menu(self) -> list[MenuItem]:
        """Build jobs submenu."""
        return [
            MenuItem(
                id="list_jobs",
                label="1. List Jobs",
                action=self._action_list_jobs,
                description="Show all jobs",
            ),
            MenuItem(
                id="cancel_job",
                label="2. Cancel Job",
                action=self._action_cancel_job_menu,
                description="Cancel a running job",
            ),
            MenuItem(
                id="back",
                label="3. Back to Main Menu",
                action=self._action_back,
                description="Return to main menu",
            ),
        ]

    def _action_list_jobs(self) -> str | None:
        """List all jobs."""
        if not self._orchestrator or not self._engine:
            return "Services not initialized"

        try:
            jobs = self._orchestrator.list_jobs()

            if not jobs:
                return "No jobs found"

            items: list[MenuItem] = []

            for job in jobs:
                # Format: [STATE] job_id (type) progress%
                state_str = job.state.name[:4] if job.state else "????"
                progress_str = f"{int(job.progress * 100)}%" if job.progress else "0%"
                type_str = job.type.name if job.type else "?"

                label = f"[{state_str}] {job.job_id[:8]}... ({type_str}) {progress_str}"

                items.append(
                    MenuItem(
                        id=job.job_id,
                        label=label,
                        description=f"Job {job.job_id}",
                    )
                )

            items.append(MenuItem(id="back", label="<< Back", action=self._action_back))

            self._engine.push_menu("Jobs List", items)
            return None

        except Exception as e:
            logger.error(f"Failed to list jobs: {e}")
            return f"Error: {e}"

    def _action_cancel_job_menu(self) -> str | None:
        """Show cancel job menu."""
        if not self._orchestrator or not self._engine:
            return "Services not initialized"

        try:
            from audiomason.core.jobs.model import JobState

            jobs = self._orchestrator.list_jobs()
            # Only show running/pending jobs
            cancellable = [j for j in jobs if j.state in (JobState.RUNNING, JobState.PENDING)]

            if not cancellable:
                return "No cancellable jobs"

            items: list[MenuItem] = []

            for job in cancellable:
                state_str = job.state.name[:4] if job.state else "????"
                label = f"[{state_str}] {job.job_id[:8]}..."

                job_id = job.job_id

                def make_cancel(jid: str) -> Any:
                    def cancel() -> str | None:
                        return self._cancel_job(jid)

                    return cancel

                items.append(
                    MenuItem(
                        id=job.job_id,
                        label=label,
                        action=make_cancel(job_id),
                        description=f"Cancel {job.job_id}",
                    )
                )

            items.append(MenuItem(id="back", label="<< Back", action=self._action_back))

            self._engine.push_menu("Cancel Job", items)
            return None

        except Exception as e:
            logger.error(f"Failed to build cancel menu: {e}")
            return f"Error: {e}"

    def _cancel_job(self, job_id: str) -> str | None:
        """Cancel a job."""
        if not self._orchestrator or not self._engine:
            return "Services not initialized"

        try:
            if self._engine.confirm_dialog(f"Cancel job {job_id[:8]}...?"):
                self._orchestrator.cancel(job_id)
                logger.info(f"Job {job_id} cancelled")

                self._engine.pop_menu()
                self._action_cancel_job_menu()

                return f"Job {job_id[:8]}... cancelled"
            else:
                return "Cancelled"

        except Exception as e:
            logger.error(f"Failed to cancel job {job_id}: {e}")
            return f"Error: {e}"

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    def _build_config_menu(self) -> list[MenuItem]:
        """Build configuration submenu."""
        return [
            MenuItem(
                id="view_config",
                label="1. View All Config",
                action=self._action_view_config,
                description="Show effective configuration",
            ),
            MenuItem(
                id="back",
                label="2. Back to Main Menu",
                action=self._action_back,
                description="Return to main menu",
            ),
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
                # Format: key = value (source)
                value_str = str(item.value)
                if len(value_str) > 30:
                    value_str = value_str[:27] + "..."

                label = f"{item.key} = {value_str}"
                desc = f"Source: {item.source}"

                items.append(
                    MenuItem(
                        id=item.key,
                        label=label,
                        description=desc,
                    )
                )

            items.append(MenuItem(id="back", label="<< Back", action=self._action_back))

            self._engine.push_menu("Configuration", items)
            return None

        except Exception as e:
            logger.error(f"Failed to view config: {e}")
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
