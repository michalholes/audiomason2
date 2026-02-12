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


CONFIG_TYPE_ANY = "any"
CONFIG_TYPE_STRING = "string"
CONFIG_TYPE_INT = "int"
CONFIG_TYPE_BOOL = "bool"
CONFIG_TYPE_ENUM = "enum"
CONFIG_TYPE_LIST = "list"
CONFIG_TYPE_OBJECT = "object"
CONFIG_TYPE_PATH = "path"


@dataclass(frozen=True)
class ConfigKeySchema:
    """Schema metadata for a single config key.

    This schema is resolver-level infrastructure. UI and other consumers may use
    it for deterministic key listing and for type hints / validation.
    """

    key_path: str
    type: str
    description: str = ""
    default: Any | None = None
    enum_values: list[str] | None = None
    allow_numeric_strings: bool = False
    allow_bool_strings: bool = False
    unknown: bool = False


class ConfigSchema:
    """Registry of known config keys and their metadata."""

    def __init__(self, keys: dict[str, ConfigKeySchema]) -> None:
        self._keys = dict(keys)

    @classmethod
    def from_defaults(cls, defaults: dict[str, Any]) -> ConfigSchema:
        keys: dict[str, ConfigKeySchema] = {}
        for key_path, value in _flatten_items(defaults):
            keys[key_path] = ConfigKeySchema(
                key_path=key_path,
                type=_infer_schema_type(value),
                default=value,
            )
        return cls(keys)

    def list_known_keys(self) -> list[str]:
        return sorted(self._keys.keys())

    def get(self, key_path: str) -> ConfigKeySchema | None:
        return self._keys.get(key_path)


def _infer_schema_type(value: Any) -> str:
    if isinstance(value, bool):
        return CONFIG_TYPE_BOOL
    if isinstance(value, int):
        return CONFIG_TYPE_INT
    if isinstance(value, list):
        return CONFIG_TYPE_LIST
    if isinstance(value, dict):
        return CONFIG_TYPE_OBJECT
    if value is None:
        return CONFIG_TYPE_ANY
    if isinstance(value, str):
        return CONFIG_TYPE_STRING
    return CONFIG_TYPE_ANY


def _flatten_items(data: dict[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    """Flatten nested dicts to dot-notation key paths.

    For lists and scalars, the current prefix becomes the leaf key.
    For dicts, recursion continues.
    """
    items: list[tuple[str, Any]] = []

    for key, value in data.items():
        key_path = f"{prefix}.{key}" if prefix else str(key)

        if isinstance(value, dict):
            items.extend(_flatten_items(value, key_path))
        else:
            items.append((key_path, value))

    return items


def _flatten_keys(data: dict[str, Any], prefix: str = "") -> set[str]:
    return {k for k, _v in _flatten_items(data, prefix=prefix)}


@dataclass(frozen=True)
class LoggingPolicy:
    """Resolved, immutable logging policy.

    This is resolver-level only and must not couple to any logging library.
    """

    level_name: str  # quiet | normal | verbose | debug
    emit_error: bool
    emit_warning: bool
    emit_info: bool
    emit_progress: bool
    emit_debug: bool
    sources: dict[str, ConfigSource]


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
        schema: ConfigSchema | None = None,
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

        self.schema = schema or ConfigSchema.from_defaults(self.defaults)

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

        Backwards compatible alias (resolver-only):
            verbosity -> logging.level

        Raises:
            ConfigError: If the resolved value is invalid.
        """
        level, _src = self._resolve_logging_level_and_source()
        return level

    def resolve_logging_policy(self) -> LoggingPolicy:
        """Resolve canonical logging policy.

        This is deterministic and side-effect free. It does not change runtime
        logging behavior; it only resolves a structured policy.
        """
        level_name = self.resolve_logging_level()
        src = self._resolve_logging_level_source()

        if level_name == "quiet":
            emit_error = True
            emit_warning = True
            emit_info = False
            emit_progress = False
            emit_debug = False
        elif level_name == "normal":
            emit_error = True
            emit_warning = True
            emit_info = True
            emit_progress = True
            emit_debug = False
        else:
            # verbose and debug
            emit_error = True
            emit_warning = True
            emit_info = True
            emit_progress = True
            emit_debug = True

        return LoggingPolicy(
            level_name=level_name,
            emit_error=emit_error,
            emit_warning=emit_warning,
            emit_info=emit_info,
            emit_progress=emit_progress,
            emit_debug=emit_debug,
            sources={"level_name": src},
        )

    def resolve_system_log_enabled(self) -> bool:
        """Resolve and validate logging.system_log_enabled."""
        key = "logging.system_log_enabled"
        value, _src = self.resolve(key)
        if not isinstance(value, bool):
            raise ConfigError(f"Config key '{key}' must be a bool, got {type(value).__name__}")
        return value

    def resolve_system_log_path(self) -> str:
        """Resolve and validate logging.system_log_path."""
        key = "logging.system_log_path"
        value, _src = self.resolve(key)
        if not isinstance(value, str):
            raise ConfigError(f"Config key '{key}' must be a string, got {type(value).__name__}")
        if value.strip() == "":
            raise ConfigError(f"Config key '{key}' must not be empty")
        return value

    def _resolve_logging_level_source(self) -> ConfigSource:
        _level, src = self._resolve_logging_level_and_source()
        return src

    def _resolve_logging_level_and_source(self) -> tuple[str, ConfigSource]:
        key = "logging.level"
        found = self._try_resolve_value(key)
        if found is None:
            # Resolver-only alias
            found = self._try_resolve_value("verbosity")

        if found is None:
            return DEFAULT_LOGGING_LEVEL, ConfigSource(
                value=DEFAULT_LOGGING_LEVEL,
                source="default",
            )

        value, source = found
        norm = self._normalize_logging_level(key, value)
        return norm, ConfigSource(value=norm, source=source)

    def _try_resolve_value(self, key: str) -> tuple[Any, str] | None:
        try:
            return self.resolve(key)
        except ConfigError as e:
            if "not found in any source" in str(e):
                return None
            raise

    def _normalize_logging_level(self, key: str, value: Any) -> str:
        if not isinstance(value, str):
            raise ConfigError(f"Config key '{key}' must be a string, got {type(value).__name__}")

        norm = value.strip().lower()
        if norm == "":
            raise ConfigError(f"Config key '{key}' must not be empty")

        if norm not in ALLOWED_LOGGING_LEVELS:
            allowed = ", ".join(sorted(ALLOWED_LOGGING_LEVELS))
            raise ConfigError(f"Invalid '{key}': {value!r}. Allowed values: {allowed}")

        return norm

    def list_known_keys(self) -> list[str]:
        """Return a deterministic list of known keys (schema-driven)."""
        return self.schema.list_known_keys()

    def get_key_schema(self, key_path: str) -> ConfigKeySchema:
        """Return schema metadata for a key.

        Unknown keys are allowed (Variant B) and will be returned as type 'any'
        with unknown=True.
        """
        known = self.schema.get(key_path)
        if known is not None:
            return known
        return ConfigKeySchema(
            key_path=key_path,
            type=CONFIG_TYPE_ANY,
            unknown=True,
        )

    def validate_value(self, key_path: str, value: Any) -> None:
        """Validate a value against schema (no coercion).

        Unknown keys are not validated.
        """
        schema = self.get_key_schema(key_path)
        if schema.unknown:
            return

        if value is None:
            return

        t = schema.type
        if t == CONFIG_TYPE_ANY:
            return
        if t == CONFIG_TYPE_STRING:
            if not isinstance(value, str):
                raise ConfigError(
                    f"Config key '{key_path}' must be a string, got {type(value).__name__}"
                )
            return
        if t == CONFIG_TYPE_INT:
            if isinstance(value, int):
                return
            if schema.allow_numeric_strings and isinstance(value, str) and value.isdigit():
                return
            raise ConfigError(f"Config key '{key_path}' must be an int")
        if t == CONFIG_TYPE_BOOL:
            if isinstance(value, bool):
                return
            if (
                schema.allow_bool_strings
                and isinstance(value, str)
                and value.lower() in {"true", "false"}
            ):
                return
            raise ConfigError(f"Config key '{key_path}' must be a bool")
        if t == CONFIG_TYPE_ENUM:
            if not isinstance(value, str):
                raise ConfigError(f"Config key '{key_path}' must be a string enum")
            if not schema.enum_values:
                raise ConfigError(f"Config key '{key_path}' has no enum_values defined")
            if value not in schema.enum_values:
                allowed = ", ".join(schema.enum_values)
                raise ConfigError(f"Invalid '{key_path}': {value!r}. Allowed values: {allowed}")
            return
        if t == CONFIG_TYPE_LIST:
            if not isinstance(value, list):
                raise ConfigError(f"Config key '{key_path}' must be a list")
            return
        if t == CONFIG_TYPE_OBJECT:
            if not isinstance(value, dict):
                raise ConfigError(f"Config key '{key_path}' must be an object")
            return
        if t == CONFIG_TYPE_PATH:
            if not isinstance(value, str):
                raise ConfigError(f"Config key '{key_path}' must be a path string")
            return

        raise ConfigError(f"Unknown schema type for '{key_path}': {t!r}")

    def resolve_all(self) -> dict[str, ConfigSource]:
        """Resolve all known config keys.

        Known keys come from the resolver schema (defaults-derived unless an
        explicit schema was provided). Unknown keys found in user/system config
        are also included (Variant B).

        Returns:
            Dict of key -> ConfigSource
        """
        result: dict[str, ConfigSource] = {}

        all_keys: set[str] = set(self.list_known_keys())

        # Explicit CLI keys (may include keys not present in defaults-derived schema).
        all_keys.update(self.cli_args.keys())

        # Unknown keys: include nested leaves from configs/defaults.
        all_keys.update(_flatten_keys(self._get_user_config()))
        all_keys.update(_flatten_keys(self._get_system_config()))
        all_keys.update(_flatten_keys(self.defaults))

        for key in sorted(all_keys):
            try:
                value, source = self.resolve(key)
                result[key] = ConfigSource(value=value, source=source)
            except ConfigError:
                continue

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
                "system_log_enabled": False,
                "system_log_path": str(Path.home() / ".audiomason" / "system.log"),
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
