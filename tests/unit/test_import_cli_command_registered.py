from __future__ import annotations

from plugins.cli.plugin import CLIPlugin


def test_import_cli_command_is_registered_via_manifest() -> None:
    """The built-in import CLI command must be discoverable from manifests only."""
    cli = CLIPlugin()
    stubs = cli._build_plugin_cli_stub_registry(plugin_dirs=None)
    assert "import" in stubs
    _plugin_dir, plugin_name = stubs["import"]
    assert plugin_name == "import_cli"
