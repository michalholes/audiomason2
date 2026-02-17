"""API module for plugin management.

Provides REST API endpoints for managing plugins.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Any

from audiomason.core import PluginLoader
from audiomason.core.config_service import ConfigService
from audiomason.core.errors import PluginError
from audiomason.core.plugin_registry import PluginRegistry


class PluginAPI:
    """Plugin management API."""

    def __init__(
        self,
        plugins_dir: Path,
        *,
        config_service: ConfigService | None = None,
        registry: PluginRegistry | None = None,
    ) -> None:
        """Initialize plugin API.

        Args:
            plugins_dir: Plugins directory
            config_service: Host config service (optional)
            registry: Plugin registry (optional)
        """
        self.plugins_dir = plugins_dir
        self._config_service = config_service or ConfigService()
        self._registry = registry or PluginRegistry(self._config_service)
        self.loader = PluginLoader(builtin_plugins_dir=plugins_dir, registry=self._registry)

    def list_plugins(self) -> list[dict[str, Any]]:
        """List all plugins.

        Returns:
            List of plugin info dicts
        """
        plugins: list[dict[str, Any]] = []

        for plugin_dir in sorted(self.plugins_dir.iterdir(), key=lambda p: p.name):
            if not plugin_dir.is_dir():
                continue

            manifest_file = plugin_dir / "plugin.yaml"
            if not manifest_file.exists():
                continue

            manifest = self.loader.load_manifest_only(plugin_dir)
            plugin_id = manifest.name

            plugins.append(
                {
                    "name": plugin_id,
                    "version": manifest.version or "unknown",
                    "description": manifest.description or "",
                    "author": manifest.author or "",
                    "enabled": self._registry.is_enabled(plugin_id),
                    "has_config": bool(manifest.config_schema),
                    "interfaces": list(manifest.interfaces),
                }
            )

        return plugins

    def get_plugin(self, name: str) -> dict[str, Any]:
        """Get plugin details.

        Args:
            name: Plugin name

        Returns:
            Plugin info dict
        """
        plugin_dir = self.plugins_dir / name
        if not plugin_dir.exists():
            raise PluginError(f"Plugin not found: {name}")

        manifest = self.loader.load_manifest_only(plugin_dir)

        return {
            "name": manifest.name,
            "version": manifest.version,
            "description": manifest.description,
            "author": manifest.author,
            "license": manifest.license,
            "enabled": self._registry.is_enabled(manifest.name),
            "config": self._registry.get_plugin_config(manifest.name),
            "config_schema": manifest.config_schema,
            "interfaces": list(manifest.interfaces),
            "dependencies": manifest.dependencies,
        }

    def enable_plugin(self, name: str) -> dict[str, str]:
        """Enable plugin."""
        self._registry.set_enabled(name, True)
        return {"message": f"Plugin '{name}' enabled"}

    def disable_plugin(self, name: str) -> dict[str, str]:
        """Disable plugin."""
        self._registry.set_enabled(name, False)
        return {"message": f"Plugin '{name}' disabled"}

    def delete_plugin(self, name: str) -> dict[str, str]:
        """Delete plugin."""
        plugin_dir = self.plugins_dir / name

        if not plugin_dir.exists():
            raise PluginError(f"Plugin not found: {name}")

        shutil.rmtree(plugin_dir)

        return {"message": f"Plugin '{name}' deleted"}

    def get_plugin_config(self, name: str) -> dict[str, Any]:
        """Get plugin configuration."""
        return self._registry.get_plugin_config(name)

    def update_plugin_config(self, name: str, config: dict[str, Any]) -> dict[str, str]:
        """Update plugin configuration."""
        self._registry.set_plugin_config(name, config)
        return {"message": f"Plugin '{name}' configuration updated"}

    def install_plugin(self, source: Path | str, method: str = "zip") -> dict[str, str]:
        """Install plugin.

        Args:
            source: Plugin source (path to ZIP or URL)
            method: Installation method (zip, url)

        Returns:
            Success message with plugin name
        """
        if method == "zip":
            return self._install_from_zip(Path(source))
        if method == "url":
            return self._install_from_url(str(source))
        raise PluginError(f"Unknown installation method: {method}")

    def _install_from_zip(self, zip_path: Path) -> dict[str, str]:
        """Install plugin from ZIP."""
        if not zip_path.exists():
            raise PluginError(f"ZIP file not found: {zip_path}")

        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(temp_path)

            plugin_yaml: Path | None = None
            for file in temp_path.rglob("plugin.yaml"):
                plugin_yaml = file
                break

            if plugin_yaml is None:
                raise PluginError("No plugin.yaml found in ZIP")

            plugin_dir = plugin_yaml.parent

            import yaml

            with open(plugin_yaml) as f:
                manifest = yaml.safe_load(f)

            plugin_name = manifest.get("name")
            if not plugin_name:
                raise PluginError("Plugin name not specified in manifest")

            target_dir = self.plugins_dir / plugin_name
            if target_dir.exists():
                raise PluginError(f"Plugin already exists: {plugin_name}")

            shutil.copytree(plugin_dir, target_dir)

        return {"message": f"Plugin '{plugin_name}' installed successfully", "name": plugin_name}

    def _install_from_url(self, url: str) -> dict[str, str]:
        """Install plugin from URL."""
        import tempfile
        import urllib.request

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            urllib.request.urlretrieve(url, temp_path)

        try:
            result = self._install_from_zip(temp_path)
        finally:
            temp_path.unlink()

        return result
