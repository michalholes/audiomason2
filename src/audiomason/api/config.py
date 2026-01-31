"""API module for configuration management.

Provides REST API endpoints for managing configuration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class ConfigAPI:
    """Configuration management API."""

    def __init__(self, config_file: Path) -> None:
        """Initialize config API.

        Args:
            config_file: Path to config file
        """
        self.config_file = config_file
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from file."""
        if self.config_file.exists():
            import yaml

            with open(self.config_file) as f:
                self.config = yaml.safe_load(f) or {}
        else:
            self.config = self._get_defaults()

    def _save_config(self) -> None:
        """Save configuration to file."""
        import yaml

        with open(self.config_file, "w") as f:
            yaml.safe_dump(self.config, f, default_flow_style=False)

    def _get_defaults(self) -> dict[str, Any]:
        """Get default configuration.

        Returns:
            Default config dict
        """
        return {
            "input_dir": str(Path.home() / "Audiobooks" / "input"),
            "output_dir": str(Path.home() / "Audiobooks" / "output"),
            "bitrate": "128k",
            "loudnorm": False,
            "split_chapters": False,
            "web_server": {
                "host": "0.0.0.0",
                "port": 8080,
            },
            "daemon": {
                "watch_folders": [],
                "interval": 30,
            },
        }

    def get_config(self) -> dict[str, Any]:
        """Get current configuration.

        Returns:
            Config dict
        """
        return self.config.copy()

    def get_config_schema(self) -> dict[str, Any]:
        """Get configuration schema.

        Returns:
            Schema defining config structure and types
        """
        return {
            "input_dir": {
                "type": "string",
                "label": "Input Directory",
                "description": "Directory where AudioMason looks for files to process",
                "default": str(Path.home() / "Audiobooks" / "input"),
            },
            "output_dir": {
                "type": "string",
                "label": "Output Directory",
                "description": "Directory for processed audiobooks",
                "default": str(Path.home() / "Audiobooks" / "output"),
            },
            "bitrate": {
                "type": "choice",
                "label": "Default Bitrate",
                "description": "Audio bitrate for MP3 conversion",
                "choices": ["96k", "128k", "192k", "256k", "320k"],
                "default": "128k",
            },
            "loudnorm": {
                "type": "boolean",
                "label": "Loudness Normalization",
                "description": "Enable loudness normalization",
                "default": False,
            },
            "split_chapters": {
                "type": "boolean",
                "label": "Split Chapters",
                "description": "Split M4A files by chapters",
                "default": False,
            },
            "web_server": {
                "type": "object",
                "label": "Web Server",
                "properties": {
                    "host": {
                        "type": "string",
                        "label": "Host",
                        "description": "Server bind address",
                        "default": "0.0.0.0",
                    },
                    "port": {
                        "type": "integer",
                        "label": "Port",
                        "description": "Server port number",
                        "default": 8080,
                    },
                },
            },
            "daemon": {
                "type": "object",
                "label": "Daemon Mode",
                "properties": {
                    "watch_folders": {
                        "type": "array",
                        "label": "Watch Folders",
                        "description": "Folders to monitor for new files",
                        "items": {"type": "string"},
                        "default": [],
                    },
                    "interval": {
                        "type": "integer",
                        "label": "Check Interval (seconds)",
                        "description": "How often to check for new files",
                        "default": 30,
                    },
                },
            },
        }

    def update_config(self, updates: dict[str, Any]) -> dict[str, str]:
        """Update configuration.

        Args:
            updates: Config updates

        Returns:
            Success message
        """
        # Deep merge
        self._deep_merge(self.config, updates)
        self._save_config()

        return {"message": "Configuration updated"}

    def _deep_merge(self, base: dict, updates: dict) -> None:
        """Deep merge updates into base dict.

        Args:
            base: Base dict (modified in place)
            updates: Updates to merge
        """
        for key, value in updates.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def reset_config(self) -> dict[str, str]:
        """Reset configuration to defaults.

        Returns:
            Success message
        """
        self.config = self._get_defaults()
        self._save_config()

        return {"message": "Configuration reset to defaults"}
