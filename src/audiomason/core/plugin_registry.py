"""PluginRegistry: single source of truth for plugin enabled/disabled state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from audiomason.core.config_service import ConfigService


@dataclass(frozen=True)
class PluginState:
    plugin_id: str
    enabled: bool


class PluginRegistry:
    """Persist and query plugin enabled/disabled state.

    The state is stored in the user config file via ConfigService.

    Storage keys:
        plugin_registry.disabled: ["plugin_a", "plugin_b", ...]  (preferred)
        plugins.disabled: ["plugin_a", "plugin_b", ...]          (legacy fallback)

    Writes always go to plugin_registry.disabled.
    """

    def __init__(self, config: ConfigService) -> None:
        self._config = config

    def _get_disabled(self) -> list[str]:
        try:
            cfg = self._config.get_config()
        except Exception:
            return []

        # Preferred location
        reg = cfg.get("plugin_registry")
        if isinstance(reg, dict):
            disabled = reg.get("disabled")
            if isinstance(disabled, list):
                return [str(x) for x in disabled]

        # Legacy fallback
        plugins = cfg.get("plugins")
        if not isinstance(plugins, dict):
            return []
        disabled = plugins.get("disabled")
        if not isinstance(disabled, list):
            return []
        return [str(x) for x in disabled]

    def is_enabled(self, plugin_id: str) -> bool:
        disabled = set(self._get_disabled())
        return plugin_id not in disabled

    def list_states(self, plugin_ids: list[str]) -> list[PluginState]:
        disabled = set(self._get_disabled())
        return [PluginState(plugin_id=pid, enabled=pid not in disabled) for pid in plugin_ids]

    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        disabled = self._get_disabled()
        if enabled:
            disabled = [x for x in disabled if x != plugin_id]
        else:
            if plugin_id not in disabled:
                disabled.append(plugin_id)
        self._config.set_value("plugin_registry.disabled", disabled)

    def get_plugin_config(self, plugin_id: str) -> dict[str, Any]:
        """Return the effective plugin config mapping.

        Reads from host user config under: plugins.<plugin_id>.config
        """
        try:
            cfg = self._config.get_config()
        except Exception:
            return {}

        plugins = cfg.get("plugins")
        if not isinstance(plugins, dict):
            return {}

        plugin_node = plugins.get(plugin_id)
        if not isinstance(plugin_node, dict):
            return {}

        cfg_node = plugin_node.get("config")
        if not isinstance(cfg_node, dict):
            return {}

        return dict(cfg_node)

    def set_plugin_config(self, plugin_id: str, config: dict[str, Any]) -> None:
        """Write plugin config mapping into host user config."""
        if not isinstance(config, dict):
            raise TypeError("config must be a dict")
        self._config.set_value(f"plugins.{plugin_id}.config", dict(config))

    def ensure_plugin_config_defaults(self, plugin_id: str, config_schema: dict[str, Any]) -> bool:
        """Materialize missing defaulted config keys into host user config.

        For each schema key with a 'default' field, write the default value to:
            plugins.<plugin_id>.config.<key>

        Existing user values are never overwritten.

        Returns True if any write occurred, else False.
        """
        if not isinstance(config_schema, dict) or config_schema == {}:
            return False

        existing = self.get_plugin_config(plugin_id)
        changed = False

        for key in sorted(config_schema.keys()):
            meta = config_schema.get(key)
            if not isinstance(meta, dict):
                continue
            if "default" not in meta:
                continue
            if key in existing:
                continue
            self._config.set_value(f"plugins.{plugin_id}.config.{key}", meta["default"])
            changed = True

        return changed
