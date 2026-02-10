"""ConfigService: structured configuration access and mutation.

UI layers must not edit raw YAML configuration text.
Instead, they call this service to read effective configuration and to set
individual values.

Storage is a user config YAML file, but consumers do not interact with the file
format directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from audiomason.core.config import ALLOWED_LOGGING_LEVELS, ConfigResolver
from audiomason.core.errors import ConfigError


def _default_user_config_path() -> Path:
    return Path.home() / ".config/audiomason/config.yaml"


def _load_yaml_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ConfigError(f"Failed to load config from {path}: {e}") from e
    return data if isinstance(data, dict) else {}


def _dump_yaml_dict(data: dict[str, Any]) -> str:
    # Deterministic formatting.
    return yaml.safe_dump(
        data,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=False,
    )


def _set_nested(data: dict[str, Any], key_path: str, value: Any) -> None:
    parts = [p for p in key_path.split(".") if p]
    if not parts:
        raise ConfigError("Empty key path")

    cur: dict[str, Any] = data
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt

    cur[parts[-1]] = value


def _validate_minimal(key_path: str, value: object) -> None:
    """Minimal validation parity with resolver (logging.level only)."""
    if key_path != "logging.level":
        return

    if not isinstance(value, str):
        raise ConfigError(f"Config key '{key_path}' must be a string, got {type(value).__name__}")

    norm = value.strip().lower()
    if norm == "":
        raise ConfigError(f"Config key '{key_path}' must not be empty")

    if norm not in ALLOWED_LOGGING_LEVELS:
        allowed = ", ".join(sorted(ALLOWED_LOGGING_LEVELS))
        raise ConfigError(f"Invalid '{key_path}': {value!r}. Allowed values: {allowed}")


def _unset_nested(data: dict[str, Any], key_path: str) -> bool:
    parts = [p for p in key_path.split(".") if p]
    if not parts:
        raise ConfigError("Empty key path")

    cur: dict[str, Any] = data
    stack: list[tuple[dict[str, Any], str]] = []

    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            return False
        stack.append((cur, part))
        cur = nxt

    leaf = parts[-1]
    if leaf not in cur:
        return False

    del cur[leaf]

    # Prune empty parent mappings.
    while stack and cur == {}:
        parent, key = stack.pop()
        del parent[key]
        cur = parent

    return True


@dataclass(frozen=True)
class EffectiveConfigItem:
    key: str
    value: Any
    source: str


class ConfigService:
    """Structured configuration API for UI layers."""

    def __init__(
        self,
        *,
        cli_args: dict[str, Any] | None = None,
        user_config_path: Path | None = None,
        system_config_path: Path | None = None,
        defaults: dict[str, Any] | None = None,
    ) -> None:
        self._resolver = ConfigResolver(
            cli_args=cli_args,
            user_config_path=user_config_path or _default_user_config_path(),
            system_config_path=system_config_path,
            defaults=defaults,
        )

    @property
    def user_config_path(self) -> Path:
        return self._resolver.user_config_path

    def get_config(self) -> dict[str, Any]:
        """Return the effective config values as a nested dict."""
        resolved = self._resolver.resolve_all()
        # Resolve_all returns flattened keys. Convert to nested dict for UI.
        out: dict[str, Any] = {}
        for k, src in resolved.items():
            _set_nested(out, k, src.value)
        return out

    def get_effective_items(self) -> list[EffectiveConfigItem]:
        items: list[EffectiveConfigItem] = []
        resolved = self._resolver.resolve_all()
        for k in sorted(resolved.keys()):
            src = resolved[k]
            items.append(EffectiveConfigItem(key=k, value=src.value, source=src.source))
        return items

    def get_effective_config_snapshot(self) -> str:
        """Return an ASCII-safe YAML snapshot of effective config values."""
        flat: dict[str, Any] = {}
        for item in self.get_effective_items():
            flat[item.key] = {"value": item.value, "source": item.source}
        return _dump_yaml_dict(flat)

    def _reinit_resolver(self) -> None:
        path = self.user_config_path
        self._resolver = ConfigResolver(
            cli_args=self._resolver.cli_args,
            user_config_path=path,
            system_config_path=self._resolver.system_config_path,
            defaults=self._resolver.defaults,
        )

    def set_value(self, key_path: str, value: Any) -> None:
        """Set a value in the user config file (lowest of non-default sources)."""
        _validate_minimal(key_path, value)
        path = self.user_config_path
        data = _load_yaml_dict(path)
        _set_nested(data, key_path, value)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_dump_yaml_dict(data), encoding="utf-8")
        self._reinit_resolver()

    def unset_value(self, key_path: str) -> None:
        """Remove a key from the user config file (reset to inherit).

        This is idempotent: if the key does not exist, no change is made.
        Empty parent mappings are pruned recursively.
        """
        path = self.user_config_path
        data = _load_yaml_dict(path)

        changed = _unset_nested(data, key_path)
        if not changed:
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_dump_yaml_dict(data), encoding="utf-8")
        self._reinit_resolver()
