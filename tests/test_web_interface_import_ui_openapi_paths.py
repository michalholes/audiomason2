from __future__ import annotations

import importlib
from pathlib import Path

from plugins.cmd_interface.plugin import preload_supported_web_plugins

from audiomason.core.loader import PluginLoader


def _get_web_interface_plugin_cls() -> type:
    module = importlib.import_module("plugins.web_interface.core")
    return module.WebInterfacePlugin


def test_web_interface_openapi_contains_import_ui_editor_paths() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    plugins_dir = repo_root / "plugins"
    loader = PluginLoader(builtin_plugins_dir=plugins_dir)
    preload_supported_web_plugins(loader=loader, plugins_dir=plugins_dir)

    app = _get_web_interface_plugin_cls()().create_app(plugin_loader=loader, verbosity=0)
    spec = app.openapi()
    paths = set(spec.get("paths", {}).keys())

    required = {
        "/import/ui/config/history",
        "/import/ui/config/rollback",
        "/import/ui/config/activate",
        "/import/ui/wizard-definition",
        "/import/ui/steps-index",
        "/import/ui/wizard-definition/validate",
        "/import/ui/wizard-definition/reset",
        "/import/ui/wizard-definition/activate",
        "/import/ui/wizard-definition/history",
        "/import/ui/wizard-definition/rollback",
    }

    missing = sorted(required - paths)
    assert not missing, f"Missing OpenAPI paths: {missing}"
