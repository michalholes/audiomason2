"""PluginRegistry: single source of truth for plugin enabled/disabled state."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from audiomason.core.config_service import ConfigService
from audiomason.core.errors import PluginNotFoundError, PluginValidationError
from audiomason.core.plugin_callable_authority import (
    RegisteredWizardCallable,
    load_wizard_callable_definitions,
)

if TYPE_CHECKING:
    from audiomason.core.loader import PluginLoader, PluginManifest


@dataclass(frozen=True)
class PluginState:
    plugin_id: str
    enabled: bool


@dataclass(frozen=True)
class WizardCallableDiscoveryResult:
    """Resolved registry-owned callable publication metadata."""

    operation_id: str
    plugin_id: str
    method_name: str
    execution_mode: str
    manifest_path: Path


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
        self._wizard_callables_by_plugin: dict[str, tuple[RegisteredWizardCallable, ...]] = {}
        self._wizard_callables_by_operation: dict[str, RegisteredWizardCallable] = {}

    def _get_disabled(self) -> list[str]:
        try:
            cfg = self._config.get_config()
        except Exception:
            return []

        reg = cfg.get("plugin_registry")
        if isinstance(reg, dict):
            disabled = reg.get("disabled")
            if isinstance(disabled, list):
                return [str(x) for x in disabled]

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

    def unregister_callable_manifest(self, plugin_id: str) -> None:
        """Remove all published callable metadata for a plugin from the registry view."""
        existing_defs = self._wizard_callables_by_plugin.pop(plugin_id, ())
        for existing in existing_defs:
            current = self._wizard_callables_by_operation.get(existing.operation_id)
            if current == existing:
                self._wizard_callables_by_operation.pop(existing.operation_id, None)

    def register_callable_manifest(
        self,
        *,
        plugin_dir: Path,
        manifest: PluginManifest,
    ) -> tuple[RegisteredWizardCallable, ...]:
        """Register provider-owned callable publication data under PluginRegistry."""
        definitions = load_wizard_callable_definitions(
            plugin_id=manifest.name,
            plugin_dir=plugin_dir,
            manifest_pointer=manifest.wizard_callable_manifest_pointer,
        )
        self.unregister_callable_manifest(manifest.name)

        for definition in definitions:
            current = self._wizard_callables_by_operation.get(definition.operation_id)
            if current is not None and current.plugin_id != definition.plugin_id:
                raise PluginValidationError(
                    "Conflicting wizard callable publication for operation "
                    f"'{definition.operation_id}': {current.plugin_id} vs {definition.plugin_id}"
                )

        for definition in definitions:
            self._wizard_callables_by_operation[definition.operation_id] = definition
        self._wizard_callables_by_plugin[manifest.name] = definitions
        return definitions

    def list_wizard_callables(self) -> list[WizardCallableDiscoveryResult]:
        """Return the registry-owned callable publication view for enabled plugins."""
        return [
            WizardCallableDiscoveryResult(
                operation_id=item.operation_id,
                plugin_id=item.plugin_id,
                method_name=item.method_name,
                execution_mode=item.execution_mode,
                manifest_path=item.manifest_path,
            )
            for item in sorted(
                (
                    item
                    for item in self._wizard_callables_by_operation.values()
                    if self.is_enabled(item.plugin_id)
                ),
                key=lambda item: (item.operation_id, item.plugin_id),
            )
        ]

    def resolve_wizard_callable(self, operation_id: str) -> WizardCallableDiscoveryResult:
        """Resolve a published wizard callable strictly via enabled PluginRegistry state."""
        item = self._wizard_callables_by_operation.get(operation_id)
        if item is None:
            raise PluginNotFoundError(operation_id)
        if not self.is_enabled(item.plugin_id):
            self.unregister_callable_manifest(item.plugin_id)
            raise PluginNotFoundError(operation_id)
        return WizardCallableDiscoveryResult(
            operation_id=item.operation_id,
            plugin_id=item.plugin_id,
            method_name=item.method_name,
            execution_mode=item.execution_mode,
            manifest_path=item.manifest_path,
        )

    def discover_wizard_callable(
        self,
        *,
        loader: PluginLoader,
        operation_id: str,
    ) -> WizardCallableDiscoveryResult:
        """Populate and resolve callable authority through the core loader/registry seam."""
        for plugin_dir in loader.discover():
            manifest = loader.load_manifest_only(plugin_dir)
            if not self.is_enabled(manifest.name):
                self.unregister_callable_manifest(manifest.name)
                continue
            self.register_callable_manifest(plugin_dir=plugin_dir, manifest=manifest)
        return self.resolve_wizard_callable(operation_id)
