from __future__ import annotations

import json
from pathlib import Path

import pytest

from audiomason.core.config_service import ConfigService
from audiomason.core.errors import PluginError, PluginNotFoundError
from audiomason.core.loader import PluginLoader
from audiomason.core.plugin_registry import PluginRegistry


def _write_demo_callable_plugin(plugins_dir: Path) -> Path:
    plugin_dir = plugins_dir / "demo_plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.yaml").write_text(
        "\n".join(
            [
                "name: demo_plugin",
                "version: 1.0.0",
                "entrypoint: plugin:DemoPlugin",
                "interfaces: []",
                "wizard_callable_manifest_pointer: wizard_callable_manifest.json",
                "test_level: none",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (plugin_dir / "wizard_callable_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "operation_id": "demo.op",
                        "method_name": "run_demo",
                        "execution_mode": "inline",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return plugin_dir


def test_loader_respects_plugin_registry(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yaml"
    cfg = ConfigService(user_config_path=cfg_path)
    reg = PluginRegistry(cfg)
    reg.set_enabled("example_plugin", enabled=False)

    repo_plugins_dir = Path(__file__).resolve().parents[2] / "plugins"
    loader = PluginLoader(builtin_plugins_dir=repo_plugins_dir, registry=reg)

    example_dir = repo_plugins_dir / "example_plugin"
    assert example_dir.is_dir()

    with pytest.raises(PluginError):
        loader.load_plugin(example_dir, validate=False)


def test_public_wizard_callable_authority_surface_has_single_entrypoint() -> None:
    public_methods = sorted(
        name
        for name, value in PluginRegistry.__dict__.items()
        if "wizard_callable" in name and callable(value) and not name.startswith("_")
    )

    assert public_methods == ["resolve_wizard_callable"]


def test_load_manifest_only_does_not_publish_disabled_callable_plugin(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    plugin_dir = _write_demo_callable_plugin(plugins_dir)
    cfg = ConfigService(user_config_path=tmp_path / "config.yaml")
    reg = PluginRegistry(cfg)
    reg.set_enabled("demo_plugin", enabled=False)
    loader = PluginLoader(builtin_plugins_dir=plugins_dir, registry=reg)

    manifest = loader.load_manifest_only(plugin_dir)

    assert manifest.name == "demo_plugin"
    with pytest.raises(PluginNotFoundError):
        reg.resolve_wizard_callable("demo.op", loader=loader)


def test_load_plugin_disabled_does_not_leak_callable_authority(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    plugin_dir = _write_demo_callable_plugin(plugins_dir)
    cfg = ConfigService(user_config_path=tmp_path / "config.yaml")
    reg = PluginRegistry(cfg)
    reg.set_enabled("demo_plugin", enabled=False)
    loader = PluginLoader(builtin_plugins_dir=plugins_dir, registry=reg)

    with pytest.raises(PluginError, match="Plugin is disabled: demo_plugin"):
        loader.load_plugin(plugin_dir, validate=False)

    with pytest.raises(PluginNotFoundError):
        reg.resolve_wizard_callable("demo.op", loader=loader)


def test_resolve_wizard_callable_skips_disabled_plugin(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    _write_demo_callable_plugin(plugins_dir)
    cfg = ConfigService(user_config_path=tmp_path / "config.yaml")
    reg = PluginRegistry(cfg)
    reg.set_enabled("demo_plugin", enabled=False)
    loader = PluginLoader(builtin_plugins_dir=plugins_dir, registry=reg)

    with pytest.raises(PluginNotFoundError):
        reg.resolve_wizard_callable("demo.op", loader=loader)


def test_resolve_wizard_callable_rejects_plugin_disabled_after_publish(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    _write_demo_callable_plugin(plugins_dir)
    cfg = ConfigService(user_config_path=tmp_path / "config.yaml")
    reg = PluginRegistry(cfg)
    loader = PluginLoader(builtin_plugins_dir=plugins_dir, registry=reg)

    resolved = reg.resolve_wizard_callable("demo.op", loader=loader)

    assert resolved.plugin_id == "demo_plugin"
    reg.set_enabled("demo_plugin", enabled=False)

    with pytest.raises(PluginNotFoundError):
        reg.resolve_wizard_callable("demo.op")
