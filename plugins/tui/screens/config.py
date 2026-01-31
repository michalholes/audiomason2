"""Configuration screen - FIX #3, #4, #5, #7."""

from __future__ import annotations

from pathlib import Path
import yaml

from ..menu import Menu, MenuItem
from ..dialogs import Dialogs
from ..theme import Theme


class ConfigScreen:
    """Configuration screen."""
    
    def __init__(self, screen, theme: Theme, config: dict):
        """Initialize config screen.
        
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
        
        # Load current config
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
        with open(self.config_file, 'w') as f:
            yaml.safe_dump(self.current_config, f, default_flow_style=False)
    
    def show(self) -> str:
        """Show configuration menu.
        
        Returns:
            Selected action or "back"
        """
        items = [
            MenuItem(
                key="1",
                label="Input Directory",
                desc=self.current_config.get("input_dir", "~/Audiobooks/input"),
                action="edit:input_dir",
                visible=True
            ),
            MenuItem(
                key="2",
                label="Output Directory",
                desc=self.current_config.get("output_dir", "~/Audiobooks/output"),
                action="edit:output_dir",
                visible=True
            ),
            MenuItem(
                key="3",
                label="Bitrate",
                desc=self.current_config.get("bitrate", "128k"),
                action="edit:bitrate",
                visible=True
            ),
            MenuItem(
                key="4",
                label="Loudness Normalization",
                desc="Enabled" if self.current_config.get("loudnorm", False) else "Disabled",
                action="edit:loudnorm",
                visible=True
            ),
            MenuItem(
                key="5",
                label="Split Chapters",
                desc="Enabled" if self.current_config.get("split_chapters", False) else "Disabled",
                action="edit:split_chapters",
                visible=True
            ),
            MenuItem(
                key="6",
                label="Daemon Settings",
                desc="Configure daemon mode",
                action="daemon",
                visible=True
            ),
            MenuItem(
                key="7",
                label="Web Server Settings",
                desc="Configure web server",
                action="web",
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
        
        while True:
            # Refresh descriptions
            items[0].desc = self.current_config.get("input_dir", "~/Audiobooks/input")
            items[1].desc = self.current_config.get("output_dir", "~/Audiobooks/output")
            items[2].desc = self.current_config.get("bitrate", "128k")
            items[3].desc = "Enabled" if self.current_config.get("loudnorm", False) else "Disabled"
            items[4].desc = "Enabled" if self.current_config.get("split_chapters", False) else "Disabled"
            
            action = self.menu.show(
                title="Configuration",
                items=items,
                footer="<Select>                                             <Back>"
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
        """Edit configuration value.
        
        FIX #3, #4: Proper choice handling with Esc support.
        
        Args:
            key: Config key to edit
        """
        if key == "bitrate":
            # FIX #3, #4: Use proper choice dialog with Esc support
            current = self.current_config.get("bitrate", "128k")
            choices = ["96k", "128k", "192k", "256k", "320k"]
            
            result = self.dialogs.choice(
                title="Select Bitrate",
                prompt="Choose default audio bitrate:",
                choices=choices,
                default=current
            )
            
            # FIX #4: Actually save the value
            if result:
                self.current_config["bitrate"] = result
                self._save_config()
                
        elif key == "loudnorm":
            current = self.current_config.get("loudnorm", False)
            result = self.dialogs.confirm(
                "Enable loudness normalization?",
                default=current
            )
            self.current_config["loudnorm"] = result
            self._save_config()
            
        elif key == "split_chapters":
            current = self.current_config.get("split_chapters", False)
            result = self.dialogs.confirm(
                "Enable chapter splitting?",
                default=current
            )
            self.current_config["split_chapters"] = result
            self._save_config()
            
        elif key in ("input_dir", "output_dir"):
            current = self.current_config.get(key, "")
            result = self.dialogs.input_text(
                title=f"Edit {key.replace('_', ' ').title()}",
                prompt="Enter path:",
                default=current
            )
            
            if result:
                self.current_config[key] = result
                self._save_config()
    
    def _edit_daemon_settings(self) -> None:
        """Edit daemon settings.
        
        FIX #5, #7: Proper Esc handling and tooltips.
        """
        daemon_config = self.current_config.get("daemon", {})
        
        items = [
            MenuItem(
                key="1",
                label="Watch Folders",
                desc=f"{len(daemon_config.get('watch_folders', []))} folders",
                action="watch_folders",
                visible=True
            ),
            MenuItem(
                key="2",
                label="Check Interval",
                desc=f"{daemon_config.get('interval', 30)} seconds",
                action="interval",
                visible=True
            ),
            MenuItem(
                key="3",
                label="On Success",
                desc=daemon_config.get('on_success', 'move_to_output'),
                action="on_success",
                visible=True
            ),
            MenuItem(
                key="4",
                label="On Error",
                desc=daemon_config.get('on_error', 'move_to_error'),
                action="on_error",
                visible=True
            ),
            MenuItem(
                key="0",
                label="Back",
                desc="Return to configuration",
                action="back",
                visible=True
            ),
        ]
        
        while True:
            # Refresh descriptions
            daemon_config = self.current_config.get("daemon", {})
            items[0].desc = f"{len(daemon_config.get('watch_folders', []))} folders"
            items[1].desc = f"{daemon_config.get('interval', 30)} seconds"
            items[2].desc = daemon_config.get('on_success', 'move_to_output')
            items[3].desc = daemon_config.get('on_error', 'move_to_error')
            
            action = self.menu.show(
                title="Daemon Configuration",
                items=items,
                footer="<Select>                                             <Back>"
            )
            
            # FIX #5: Proper Esc handling
            if action == "back":
                return
            elif action == "watch_folders":
                self._edit_watch_folders()
            elif action == "interval":
                self._edit_daemon_interval()
            elif action == "on_success":
                self._edit_daemon_on_success()
            elif action == "on_error":
                self._edit_daemon_on_error()
    
    def _edit_watch_folders(self) -> None:
        """Edit daemon watch folders.
        
        FIX #7: Show tooltip/description.
        """
        daemon_config = self.current_config.setdefault("daemon", {})
        folders = daemon_config.get("watch_folders", [])
        
        # Show current folders
        if folders:
            folder_list = "\n".join(f"  - {f}" for f in folders)
            msg = f"Current watch folders:\n\n{folder_list}\n\nAdd or remove?"
        else:
            msg = "No watch folders configured.\n\nThese are directories that daemon monitors\nfor new audiobook files."
        
        self.dialogs.message("Watch Folders", msg)
        
        # Simple add dialog
        result = self.dialogs.input_text(
            title="Add Watch Folder",
            prompt="Enter folder path (or leave empty):",
            default=""
        )
        
        if result and result not in folders:
            folders.append(result)
            daemon_config["watch_folders"] = folders
            self._save_config()
    
    def _edit_daemon_interval(self) -> None:
        """Edit daemon check interval.
        
        FIX #7: Show description.
        """
        daemon_config = self.current_config.setdefault("daemon", {})
        current = daemon_config.get("interval", 30)
        
        result = self.dialogs.input_text(
            title="Check Interval",
            prompt="How often to check for new files (seconds):\n(Recommended: 30-300)",
            default=str(current)
        )
        
        if result:
            try:
                interval = int(result)
                if 5 <= interval <= 3600:
                    daemon_config["interval"] = interval
                    self._save_config()
                else:
                    self.dialogs.message("Invalid Value", "Interval must be between 5 and 3600 seconds")
            except ValueError:
                self.dialogs.message("Invalid Value", "Please enter a number")
    
    def _edit_daemon_on_success(self) -> None:
        """Edit daemon on_success action.
        
        FIX #7: Show descriptions for each choice.
        """
        daemon_config = self.current_config.setdefault("daemon", {})
        current = daemon_config.get("on_success", "move_to_output")
        
        result = self.dialogs.choice(
            title="On Success Action",
            prompt="What to do with source files after successful processing?",
            choices=["move_to_output", "keep", "delete"],
            default=current
        )
        
        if result:
            daemon_config["on_success"] = result
            self._save_config()
    
    def _edit_daemon_on_error(self) -> None:
        """Edit daemon on_error action.
        
        FIX #7: Show descriptions.
        """
        daemon_config = self.current_config.setdefault("daemon", {})
        current = daemon_config.get("on_error", "move_to_error")
        
        result = self.dialogs.choice(
            title="On Error Action",
            prompt="What to do with files that failed to process?",
            choices=["move_to_error", "keep", "delete"],
            default=current
        )
        
        if result:
            daemon_config["on_error"] = result
            self._save_config()
    
    def _edit_web_settings(self) -> None:
        """Edit web server settings."""
        web_config = self.current_config.setdefault("web_server", {})
        
        items = [
            MenuItem(
                key="1",
                label="Host",
                desc=web_config.get('host', '0.0.0.0'),
                action="host",
                visible=True
            ),
            MenuItem(
                key="2",
                label="Port",
                desc=str(web_config.get('port', 8080)),
                action="port",
                visible=True
            ),
            MenuItem(
                key="0",
                label="Back",
                desc="Return to configuration",
                action="back",
                visible=True
            ),
        ]
        
        while True:
            # Refresh descriptions
            web_config = self.current_config.get("web_server", {})
            items[0].desc = web_config.get('host', '0.0.0.0')
            items[1].desc = str(web_config.get('port', 8080))
            
            action = self.menu.show(
                title="Web Server Configuration",
                items=items,
                footer="<Select>                                             <Back>"
            )
            
            if action == "back":
                return
            elif action == "host":
                result = self.dialogs.input_text(
                    title="Edit Host",
                    prompt="Enter host address:",
                    default=web_config.get('host', '0.0.0.0')
                )
                if result:
                    web_config["host"] = result
                    self._save_config()
            elif action == "port":
                result = self.dialogs.input_text(
                    title="Edit Port",
                    prompt="Enter port number:",
                    default=str(web_config.get('port', 8080))
                )
                if result:
                    try:
                        port = int(result)
                        if 1024 <= port <= 65535:
                            web_config["port"] = port
                            self._save_config()
                        else:
                            self.dialogs.message("Invalid Port", "Port must be between 1024 and 65535")
                    except ValueError:
                        self.dialogs.message("Invalid Port", "Please enter a number")
