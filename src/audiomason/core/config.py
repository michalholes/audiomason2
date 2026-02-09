"""Configuration resolver with 4-level priority.

Priority (highest to lowest):
1. CLI arguments
2. Environment variables (AUDIOMASON_*)
3. Config files (user > system)
4. Defaults
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from audiomason.core.errors import ConfigError

ALLOWED_LOGGING_LEVELS = frozenset({"quiet", "normal", "verbose", "debug"})
DEFAULT_LOGGING_LEVEL = "normal"


@dataclass
class ConfigSource:
    """Represents where a config value came from."""

    value: Any
    source: str  # 'cli' | 'env' | 'user_config' | 'system_config' | 'default'


class ConfigResolver:
    """Resolve configuration with strict 4-level priority.

    Example:
        resolver = ConfigResolver(
            cli_args={'bitrate': '320k'},
            user_config_path=Path('~/.config/audiomason/config.yaml')
        )

        bitrate, source = resolver.resolve('bitrate')
        # bitrate = '320k', source = 'cli'
    """

    def __init__(
        self,
        cli_args: dict[str, Any] | None = None,
        user_config_path: Path | None = None,
        system_config_path: Path | None = None,
        defaults: dict[str, Any] | None = None,
    ) -> None:
        """Initialize config resolver.

        Args:
            cli_args: Arguments from CLI (highest priority)
            user_config_path: Path to user config file
            system_config_path: Path to system config file
            defaults: Default values (lowest priority)
        """
        self.cli_args = cli_args or {}
        self.user_config_path = user_config_path or Path.home() / ".config/audiomason/config.yaml"
        self.system_config_path = system_config_path or Path("/etc/audiomason/config.yaml")
        self.defaults = defaults or self._default_config()

        # Cache loaded configs
        self._user_config: dict[str, Any] | None = None
        self._system_config: dict[str, Any] | None = None

    def resolve(self, key: str) -> tuple[Any, str]:
        """Resolve config value with priority.

        Args:
            key: Config key (supports dot notation: 'logging.level')

        Returns:
            (value, source) tuple

        Raises:
            ConfigError: If key not found in any source
        """
        # 1. CLI (highest priority)
        value = self._from_cli(key)
        if value is not None:
            return value, "cli"

        # 2. Environment
        value = self._from_env(key)
        if value is not None:
            return value, "env"

        # 3. User config
        value = self._from_user_config(key)
        if value is not None:
            return value, "user_config"

        # 4. System config
        value = self._from_system_config(key)
        if value is not None:
            return value, "system_config"

        # 5. Default
        value = self._from_defaults(key)
        if value is not None:
            return value, "default"

        raise ConfigError(f"Config key '{key}' not found in any source")

    def resolve_logging_level(self) -> str:
        """Resolve and validate logging.level.

        Canonical key:
            logging.level

        Allowed values (after normalization):
            quiet | normal | verbose | debug

        If the key is not provided by any source, returns DEFAULT_LOGGING_LEVEL.

        Raises:
            ConfigError: If the resolved value is invalid.
        """
        key = "logging.level"
        try:
            value, _source = self.resolve(key)
        except ConfigError as e:
            if "not found in any source" in str(e):
                return DEFAULT_LOGGING_LEVEL
            raise

        if not isinstance(value, str):
            raise ConfigError(f"Config key '{key}' must be a string, got {type(value).__name__}")

        norm = value.strip().lower()
        if norm == "":
            raise ConfigError(f"Config key '{key}' must not be empty")

        if norm not in ALLOWED_LOGGING_LEVELS:
            allowed = ", ".join(sorted(ALLOWED_LOGGING_LEVELS))
            raise ConfigError(f"Invalid '{key}': {value!r}. Allowed values: {allowed}")

        return norm

    def resolve_all(self) -> dict[str, ConfigSource]:
        """Resolve all known config keys.

        Returns:
            Dict of key -> ConfigSource
        """
        result = {}

        # Get all possible keys
        all_keys: set[str] = set()
        all_keys.update(self.cli_args.keys())
        all_keys.update(self._get_user_config().keys())
        all_keys.update(self._get_system_config().keys())
        all_keys.update(self.defaults.keys())

        # Resolve each key
        for key in all_keys:
            try:
                value, source = self.resolve(key)
                result[key] = ConfigSource(value=value, source=source)
            except ConfigError:
                pass

        return result

    def _from_cli(self, key: str) -> Any | None:
        """Get value from CLI args."""
        return self._get_nested(self.cli_args, key)

    def _from_env(self, key: str) -> Any | None:
        """Get value from environment variables.

        Environment variable format: AUDIOMASON_KEY_NAME
        Example: AUDIOMASON_BITRATE, AUDIOMASON_OUTPUT_DIR
        """
        # Convert key to env var name
        env_key = f"AUDIOMASON_{key.upper().replace('.', '_')}"
        return os.environ.get(env_key)

    def _from_user_config(self, key: str) -> Any | None:
        """Get value from user config file."""
        config = self._get_user_config()
        return self._get_nested(config, key)

    def _from_system_config(self, key: str) -> Any | None:
        """Get value from system config file."""
        config = self._get_system_config()
        return self._get_nested(config, key)

    def _from_defaults(self, key: str) -> Any | None:
        """Get value from defaults."""
        return self._get_nested(self.defaults, key)

    def _get_user_config(self) -> dict[str, Any]:
        """Load user config file (cached)."""
        if self._user_config is None:
            self._user_config = self._load_yaml(self.user_config_path)
        return self._user_config

    def _get_system_config(self) -> dict[str, Any]:
        """Load system config file (cached)."""
        if self._system_config is None:
            self._system_config = self._load_yaml(self.system_config_path)
        return self._system_config

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        """Load YAML file."""
        if not path.exists():
            return {}

        try:
            with open(path) as f:
                data = yaml.safe_load(f)
                return data if isinstance(data, dict) else {}
        except Exception as e:
            raise ConfigError(f"Failed to load config from {path}: {e}") from e

    def _get_nested(self, data: dict[str, Any], key: str) -> Any | None:
        """Get nested value using dot notation.

        Example:
            data = {'logging': {'level': 'debug'}}
            _get_nested(data, 'logging.level') -> 'debug'
        """
        parts = key.split(".")
        current: Any = data

        for part in parts:
            if not isinstance(current, dict):
                return None
            current = current.get(part)
            if current is None:
                return None

        return current

    @staticmethod
    def _default_config() -> dict[str, Any]:
        """Default configuration."""
        return {
            # Paths
            "ffmpeg_path": "ffmpeg",
            "output_dir": str(Path.home() / "Audiobooks" / "output"),
            "inbox_dir": str(Path.home() / "Audiobooks" / "inbox"),
            "outbox_dir": str(Path.home() / "Audiobooks" / "outbox"),
            "plugins_dir": str(Path.home() / ".audiomason" / "plugins"),
            "stage_dir": "/tmp/audiomason/stage",
            # Audio
            "bitrate": "128k",
            "loudnorm": False,
            "split_chapters": False,
            "target_format": "mp3",
            # Metadata
            "metadata_providers": ["googlebooks", "openlibrary"],
            "metadata_priority": "googlebooks",
            # Covers
            "cover_preference": "embedded",
            "cover_fallback": "url",
            # Prompts
            "prompts": {
                "strategy": "smart_batch",
                "grouping": {
                    "by_directory": True,
                    "by_filename": True,
                    "by_metadata": True,
                },
            },
            # Logging
            "logging": {
                "level": "normal",
                "file": None,
                "color": True,
                "per_module": {},
            },
            # Pipeline
            "pipeline": "standard",
            # Daemon
            "daemon": {
                "watch_folders": [],
                "interval": 30,
                "on_success": "move_to_output",
                "on_error": "move_to_error",
            },
            # Plugins
            "plugins": {
                "check_updates": True,
                "auto_load": True,
            },
            # Web server
            "web": {
                "host": "0.0.0.0",
                "port": 8080,
                "upload_dir": "/tmp/audiomason/uploads",
            },
            # File I/O capability (plugin-owned)
            "file_io": {
                "roots": {
                    "inbox_dir": str(Path.home() / "Audiobooks" / "inbox"),
                    "stage_dir": "/tmp/audiomason/stage",
                    "jobs_dir": "/tmp/audiomason/jobs",
                    "outbox_dir": str(Path.home() / "Audiobooks" / "outbox"),
                },
            },
        }
