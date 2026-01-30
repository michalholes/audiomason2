"""API module for plugin management.

Provides REST API endpoints for managing plugins.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Any

from audiomason.core import PluginLoader
from audiomason.core.errors import PluginError


class PluginAPI:
    """Plugin management API."""

    def __init__(self, plugins_dir: Path) -> None:
        """Initialize plugin API.

        Args:
            plugins_dir: Plugins directory
        """
        self.plugins_dir = plugins_dir
        self.config_file = Path.home() / ".config" / "audiomason" / "plugins.yaml"
        self.loader = PluginLoader(builtin_plugins_dir=plugins_dir)
        self._load_config()

    def _load_config(self) -> None:
        """Load plugin configuration."""
        if self.config_file.exists():
            import yaml
            with open(self.config_file) as f:
                self.config = yaml.safe_load(f) or {}
        else:
            self.config = {"plugins": {}}

    def _save_config(self) -> None:
        """Save plugin configuration."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        import yaml
        with open(self.config_file, "w") as f:
            yaml.safe_dump(self.config, f)

    def list_plugins(self) -> list[dict[str, Any]]:
        """List all plugins.

        Returns:
            List of plugin info dicts
        """
        plugins = []
        
        for plugin_dir in self.plugins_dir.iterdir():
            if not plugin_dir.is_dir():
                continue
            
            manifest_file = plugin_dir / "plugin.yaml"
            if not manifest_file.exists():
                continue
            
            # Load manifest
            import yaml
            with open(manifest_file) as f:
                manifest = yaml.safe_load(f)
            
            plugin_name = plugin_dir.name
            plugin_config = self.config.get("plugins", {}).get(plugin_name, {})
            
            plugins.append({
                "name": plugin_name,
                "version": manifest.get("version", "unknown"),
                "description": manifest.get("description", ""),
                "author": manifest.get("author", ""),
                "enabled": plugin_config.get("enabled", True),
                "has_config": bool(manifest.get("config_schema")),
                "interfaces": manifest.get("interfaces", []),
            })
        
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
        
        manifest_file = plugin_dir / "plugin.yaml"
        import yaml
        with open(manifest_file) as f:
            manifest = yaml.safe_load(f)
        
        plugin_config = self.config.get("plugins", {}).get(name, {})
        
        return {
            "name": name,
            "version": manifest.get("version"),
            "description": manifest.get("description"),
            "author": manifest.get("author"),
            "license": manifest.get("license"),
            "enabled": plugin_config.get("enabled", True),
            "config": plugin_config.get("config", {}),
            "config_schema": manifest.get("config_schema", {}),
            "interfaces": manifest.get("interfaces", []),
            "dependencies": manifest.get("dependencies", {}),
        }

    def enable_plugin(self, name: str) -> dict[str, str]:
        """Enable plugin.

        Args:
            name: Plugin name

        Returns:
            Success message
        """
        if "plugins" not in self.config:
            self.config["plugins"] = {}
        
        if name not in self.config["plugins"]:
            self.config["plugins"][name] = {}
        
        self.config["plugins"][name]["enabled"] = True
        self._save_config()
        
        return {"message": f"Plugin '{name}' enabled"}

    def disable_plugin(self, name: str) -> dict[str, str]:
        """Disable plugin.

        Args:
            name: Plugin name

        Returns:
            Success message
        """
        if "plugins" not in self.config:
            self.config["plugins"] = {}
        
        if name not in self.config["plugins"]:
            self.config["plugins"][name] = {}
        
        self.config["plugins"][name]["enabled"] = False
        self._save_config()
        
        return {"message": f"Plugin '{name}' disabled"}

    def delete_plugin(self, name: str) -> dict[str, str]:
        """Delete plugin.

        Args:
            name: Plugin name

        Returns:
            Success message
        """
        plugin_dir = self.plugins_dir / name
        
        if not plugin_dir.exists():
            raise PluginError(f"Plugin not found: {name}")
        
        # Remove from config
        if "plugins" in self.config and name in self.config["plugins"]:
            del self.config["plugins"][name]
            self._save_config()
        
        # Delete files
        shutil.rmtree(plugin_dir)
        
        return {"message": f"Plugin '{name}' deleted"}

    def get_plugin_config(self, name: str) -> dict[str, Any]:
        """Get plugin configuration.

        Args:
            name: Plugin name

        Returns:
            Plugin config
        """
        plugin_config = self.config.get("plugins", {}).get(name, {})
        return plugin_config.get("config", {})

    def update_plugin_config(self, name: str, config: dict[str, Any]) -> dict[str, str]:
        """Update plugin configuration.

        Args:
            name: Plugin name
            config: New config

        Returns:
            Success message
        """
        if "plugins" not in self.config:
            self.config["plugins"] = {}
        
        if name not in self.config["plugins"]:
            self.config["plugins"][name] = {}
        
        self.config["plugins"][name]["config"] = config
        self._save_config()
        
        return {"message": f"Plugin '{name}' configuration updated"}

    def install_plugin(self, source: Path | str, method: str = "zip") -> dict[str, str]:
        """Install plugin.

        Args:
            source: Plugin source (path to ZIP or URL)
            method: Installation method (zip, url, git)

        Returns:
            Success message with plugin name
        """
        if method == "zip":
            return self._install_from_zip(Path(source))
        elif method == "url":
            return self._install_from_url(str(source))
        else:
            raise PluginError(f"Unknown installation method: {method}")

    def _install_from_zip(self, zip_path: Path) -> dict[str, str]:
        """Install plugin from ZIP.

        Args:
            zip_path: Path to ZIP file

        Returns:
            Success message
        """
        if not zip_path.exists():
            raise PluginError(f"ZIP file not found: {zip_path}")
        
        # Extract to temp
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(temp_path)
            
            # Find plugin.yaml
            plugin_yaml = None
            for file in temp_path.rglob("plugin.yaml"):
                plugin_yaml = file
                break
            
            if not plugin_yaml:
                raise PluginError("No plugin.yaml found in ZIP")
            
            plugin_dir = plugin_yaml.parent
            
            # Read plugin name
            import yaml
            with open(plugin_yaml) as f:
                manifest = yaml.safe_load(f)
            
            plugin_name = manifest.get("name")
            if not plugin_name:
                raise PluginError("Plugin name not specified in manifest")
            
            # Copy to plugins dir
            target_dir = self.plugins_dir / plugin_name
            if target_dir.exists():
                raise PluginError(f"Plugin already exists: {plugin_name}")
            
            shutil.copytree(plugin_dir, target_dir)
        
        return {"message": f"Plugin '{plugin_name}' installed successfully", "name": plugin_name}

    def _install_from_url(self, url: str) -> dict[str, str]:
        """Install plugin from URL.

        Args:
            url: Plugin URL (ZIP file)

        Returns:
            Success message
        """
        import tempfile
        import urllib.request
        
        # Download to temp
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            urllib.request.urlretrieve(url, temp_path)
        
        try:
            result = self._install_from_zip(temp_path)
        finally:
            temp_path.unlink()
        
        return result
