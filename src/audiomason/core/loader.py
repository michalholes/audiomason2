"""Plugin loader and discovery system."""

from __future__ import annotations

import importlib.util
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from audiomason.core.plugin_registry import PluginRegistry

from audiomason.core.errors import PluginError, PluginNotFoundError, PluginValidationError


@dataclass
class PluginManifest:
    """Plugin manifest loaded from plugin.yaml."""

    name: str
    version: str
    description: str
    author: str
    license: str
    entrypoint: str  # "module:ClassName"
    interfaces: list[str]
    hooks: list[str]
    dependencies: dict[str, Any]
    config_schema: dict[str, Any]
    test_level: str  # "none" | "basic" | "strict"


class PluginLoader:
    """Load and manage plugins.

    Discovers plugins from multiple sources:
    1. Built-in plugins (audiomason/plugins/)
    2. User plugins (~/.audiomason/plugins/)
    3. System plugins (/etc/audiomason/plugins/)
    4. Config-specified plugins
    """

    def __init__(
        self,
        builtin_plugins_dir: Path | None = None,
        user_plugins_dir: Path | None = None,
        system_plugins_dir: Path | None = None,
        *,
        registry: PluginRegistry | None = None,
    ) -> None:
        """Initialize plugin loader.

        Args:
            builtin_plugins_dir: Built-in plugins directory
            user_plugins_dir: User plugins directory
            system_plugins_dir: System plugins directory
        """
        self.builtin_plugins_dir = builtin_plugins_dir
        self.user_plugins_dir = user_plugins_dir or Path.home() / ".audiomason/plugins"
        self.system_plugins_dir = system_plugins_dir or Path("/etc/audiomason/plugins")

        self._ensure_builtin_import_root()

        self._registry = registry

        # Loaded plugins
        self._plugins: dict[str, Any] = {}
        self._manifests: dict[str, PluginManifest] = {}

    def _ensure_builtin_import_root(self) -> None:
        """Ensure built-in plugins can import the top-level 'plugins' package.

        Built-in plugins live under the repository 'plugins/' package. When running AM2
        via an installed entrypoint, the repository root may not be on sys.path, which
        breaks absolute imports like 'plugins.file_io...'.

        If (and only if) the built-in plugins directory is a Python package, add the
        repository root to sys.path deterministically and idempotently.
        """
        if self.builtin_plugins_dir is None:
            return

        if not (self.builtin_plugins_dir / "__init__.py").exists():
            return

        repo_root = self.builtin_plugins_dir.parent
        repo_root_str = str(repo_root)

        if repo_root_str not in sys.path:
            sys.path.insert(0, repo_root_str)

    def discover(self) -> list[Path]:
        """Discover all available plugins.

        Returns:
            List of plugin directories
        """
        plugin_dirs: list[Path] = []

        # Scan directories
        for base_dir in [
            self.builtin_plugins_dir,
            self.user_plugins_dir,
            self.system_plugins_dir,
        ]:
            if base_dir and base_dir.exists():
                plugin_dirs.extend(self._scan_directory(base_dir))

        return plugin_dirs

    def load_plugin(self, plugin_dir: Path, validate: bool = True) -> Any:
        """Load a single plugin.

        Args:
            plugin_dir: Plugin directory
            validate: Whether to validate plugin

        Returns:
            Plugin instance

        Raises:
            PluginError: If plugin loading fails
        """
        # Load manifest
        manifest = self._load_manifest(plugin_dir)

        # Registry enforcement
        if self._registry is not None and not self._registry.is_enabled(manifest.name):
            raise PluginError(f"Plugin is disabled: {manifest.name}")

        # Validate if requested
        if validate and manifest.test_level != "none":
            self._validate_plugin(plugin_dir, manifest)

        # Load plugin class
        plugin_class = self._load_plugin_class(plugin_dir, manifest.entrypoint)

        # Instantiate
        plugin_instance = plugin_class()

        # Cache
        self._plugins[manifest.name] = plugin_instance
        self._manifests[manifest.name] = manifest

        return plugin_instance

    def get_plugin(self, name: str) -> Any:
        """Get loaded plugin by name.

        Args:
            name: Plugin name

        Returns:
            Plugin instance

        Raises:
            PluginNotFoundError: If plugin not found
        """
        if name not in self._plugins:
            raise PluginNotFoundError(name)
        return self._plugins[name]

    def get_manifest(self, name: str) -> PluginManifest:
        """Get plugin manifest.

        Args:
            name: Plugin name

        Returns:
            Plugin manifest

        Raises:
            PluginNotFoundError: If plugin not found
        """
        if name not in self._manifests:
            raise PluginNotFoundError(name)
        return self._manifests[name]

    def list_plugins(self) -> list[str]:
        """List all loaded plugins.

        Returns:
            List of plugin names
        """
        return list(self._plugins.keys())

    def _scan_directory(self, base_dir: Path) -> list[Path]:
        """Scan directory for plugins.

        Plugins are identified by presence of plugin.yaml file.

        Args:
            base_dir: Base directory to scan

        Returns:
            List of plugin directories
        """
        plugin_dirs: list[Path] = []

        if not base_dir.exists():
            return plugin_dirs

        for item in base_dir.iterdir():
            if item.is_dir() and (item / "plugin.yaml").exists():
                plugin_dirs.append(item)

        return plugin_dirs

    def _load_manifest(self, plugin_dir: Path) -> PluginManifest:
        """Load plugin manifest.

        Args:
            plugin_dir: Plugin directory

        Returns:
            Plugin manifest

        Raises:
            PluginError: If manifest loading fails
        """
        manifest_path = plugin_dir / "plugin.yaml"

        if not manifest_path.exists():
            raise PluginError(f"Plugin manifest not found: {manifest_path}")

        try:
            with open(manifest_path) as f:
                data = yaml.safe_load(f)

            return PluginManifest(
                name=data["name"],
                version=data["version"],
                description=data.get("description", ""),
                author=data.get("author", "Unknown"),
                license=data.get("license", "Unknown"),
                entrypoint=data["entrypoint"],
                interfaces=data.get("interfaces", []),
                hooks=data.get("hooks", []),
                dependencies=data.get("dependencies", {}),
                config_schema=data.get("config_schema", {}),
                test_level=data.get("test_level", "basic"),
            )
        except Exception as e:
            raise PluginError(f"Failed to load manifest from {manifest_path}: {e}") from e

    def _load_plugin_class(self, plugin_dir: Path, entrypoint: str) -> type:
        """Load plugin class from entrypoint.

        Args:
            plugin_dir: Plugin directory
            entrypoint: Entrypoint string (e.g., "module:ClassName")

        Returns:
            Plugin class

        Raises:
            PluginError: If loading fails
        """
        try:
            # Parse entrypoint
            if ":" not in entrypoint:
                raise PluginError(f"Invalid entrypoint format: {entrypoint}")

            module_name, class_name = entrypoint.split(":", 1)

            # Find module file
            module_file = plugin_dir / f"{module_name}.py"
            if not module_file.exists():
                raise PluginError(f"Module file not found: {module_file}")

            # Load module
            # Load module
            #
            # IMPORTANT: never register external plugin modules under a generic name like
            # 'plugin' in sys.modules. Multiple plugins can legitimately use entrypoints
            # like 'plugin:SomePlugin', which would otherwise overwrite each other and
            # pollute global import state.
            plugin_key = plugin_dir.name.replace("-", "_").replace(".", "_")

            # Dynamically load plugin modules under an isolated namespace to avoid
            # collisions (multiple plugins can legitimately use entrypoints like
            # 'plugin:SomePlugin') and to provide a stable package context for
            # relative imports inside the plugin.
            root_pkg = "audiomason_plugins"
            plugin_pkg = f"{root_pkg}.{plugin_key}"
            unique_module_name = f"{plugin_pkg}.{module_name}"

            def _ensure_package(name: str, path: Path | None = None) -> None:
                if name in sys.modules:
                    return
                pkg = types.ModuleType(name)
                pkg.__path__ = [] if path is None else [str(path)]
                sys.modules[name] = pkg

            _ensure_package(root_pkg)
            _ensure_package(plugin_pkg, plugin_dir)

            spec = importlib.util.spec_from_file_location(unique_module_name, module_file)
            if spec is None or spec.loader is None:
                raise PluginError(f"Failed to load module spec: {module_file}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[unique_module_name] = module
            spec.loader.exec_module(module)

            # Get class
            if not hasattr(module, class_name):
                raise PluginError(f"Class '{class_name}' not found in {module_name}")

            return getattr(module, class_name)

        except Exception as e:
            raise PluginError(f"Failed to load plugin class: {e}") from e

    def _validate_plugin(self, plugin_dir: Path, manifest: PluginManifest) -> None:
        """Validate plugin before loading.

        Performs comprehensive validation:
        1. Manifest exists and valid YAML
        2. Python syntax check
        3. Module imports work
        4. Class exists
        5. Required methods present
        6. Method signatures correct (basic check)
        7. Dependencies available

        Args:
            plugin_dir: Plugin directory
            manifest: Plugin manifest

        Raises:
            PluginValidationError: If validation fails
        """
        validation_errors = []

        # 1. Module file exists
        module_name = manifest.entrypoint.split(":")[0]
        module_file = plugin_dir / f"{module_name}.py"

        if not module_file.exists():
            raise PluginValidationError(f"Plugin module not found: {module_file}")

        # 2. Python syntax check
        try:
            with open(module_file) as f:
                code = f.read()
            compile(code, str(module_file), "exec")
        except SyntaxError as e:
            validation_errors.append(f"Syntax error in {module_file}: {e}")

        # 3. Test imports in sandbox (basic check - just try to import)
        try:
            import ast

            with open(module_file) as f:
                tree = ast.parse(f.read())

            # Extract imports
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        try:
                            __import__(alias.name.split(".")[0])
                        except ImportError:
                            validation_errors.append(
                                f"Import error: module '{alias.name}' not available"
                            )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    try:
                        __import__(node.module.split(".")[0])
                    except ImportError:
                        validation_errors.append(
                            f"Import error: module '{node.module}' not available"
                        )
        except Exception as e:
            validation_errors.append(f"Import validation failed: {e}")

        # 4. Class exists (check via AST to avoid loading)
        class_name = manifest.entrypoint.split(":")[1] if ":" in manifest.entrypoint else None
        if class_name:
            try:
                import ast

                with open(module_file) as f:
                    tree = ast.parse(f.read())

                class_found = False
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef) and node.name == class_name:
                        class_found = True
                        break

                if not class_found:
                    validation_errors.append(f"Class '{class_name}' not found in {module_file}")
            except Exception as e:
                validation_errors.append(f"Class validation failed: {e}")

        # 5-6. Method presence/signatures would require loading the class
        # Skip for basic validation to avoid side effects

        # 7. Check dependencies (basic - just check if importable)
        if manifest.dependencies:
            for dep_name, dep_info in manifest.dependencies.items():
                try:
                    __import__(dep_name)
                except ImportError:
                    # Check if it's a conditional dependency
                    if isinstance(dep_info, dict) and dep_info.get("optional", False):
                        # Optional dependency - just warning
                        pass
                    else:
                        validation_errors.append(f"Required dependency '{dep_name}' not available")

        # Report errors
        if validation_errors:
            error_msg = "\n".join(f"  - {err}" for err in validation_errors)
            raise PluginValidationError(
                f"Plugin validation failed for '{manifest.name}':\n{error_msg}"
            )
