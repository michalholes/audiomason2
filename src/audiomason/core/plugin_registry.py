"""PluginRegistry: single source of truth for plugin enabled/disabled state."""

from __future__ import annotations

from dataclasses import dataclass

from audiomason.core.config_service import ConfigService


@dataclass(frozen=True)
class PluginState:
    plugin_id: str
    enabled: bool


class PluginRegistry:
    """Persist and query plugin enabled/disabled state.

    The state is stored in the user config file via ConfigService under:
        plugins.disabled: ["plugin_a", "plugin_b", ...]

    This keeps a single source of truth that both CLI and Web can share.
    """

    def __init__(self, config: ConfigService) -> None:
        self._config = config

    def _get_disabled(self) -> list[str]:
        try:
            cfg = self._config.get_config()
        except Exception:
            return []
        plugins = cfg.get("plugins")
        if not isinstance(plugins, dict):
            return []
        disabled = plugins.get("disabled")
        if not isinstance(disabled, list):
            return []
        return [str(x) for x in disabled]

    def list_states(self, plugin_ids: list[str]) -> list[PluginState]:
        disabled = set(self._get_disabled())
        out: list[PluginState] = []
        for pid in plugin_ids:
            out.append(PluginState(plugin_id=pid, enabled=pid not in disabled))
        return out

    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        disabled = self._get_disabled()
        if enabled:
            disabled = [x for x in disabled if x != plugin_id]
        else:
            if plugin_id not in disabled:
                disabled.append(plugin_id)
        # Write back via ConfigService.
        self._config.set_value("plugins.disabled", disabled)
