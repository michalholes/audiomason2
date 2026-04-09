from __future__ import annotations

import importlib
from pathlib import Path

from audiomason.core.loader import PluginLoader


def test_supported_web_launch_path_preloads_import_plugin() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    plugins_dir = repo_root / "plugins"
    loader = PluginLoader(builtin_plugins_dir=plugins_dir)

    cmd_plugin = importlib.import_module("plugins.cmd_interface.plugin")
    web_core = importlib.import_module("plugins.web_interface.core")

    cmd_plugin.preload_supported_web_plugins(loader=loader, plugins_dir=plugins_dir)

    import_plugin = loader.get_plugin("import")
    assert import_plugin is not None

    app = web_core.WebInterfacePlugin().create_app(plugin_loader=loader, verbosity=0)
    paths = set(app.openapi().get("paths", {}).keys())

    assert "/import/ui/config/history" in paths
    assert "/import/ui/wizard-definition" in paths
