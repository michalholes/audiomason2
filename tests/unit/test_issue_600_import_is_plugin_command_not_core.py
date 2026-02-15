"""Regression: Issue 600 - import is a plugin command, not a core CLI dispatch."""

from __future__ import annotations

from pathlib import Path

from plugins.cli.plugin import CLIPlugin


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_import_is_plugin_command_not_core() -> None:
    repo_root = _repo_root()

    cli_plugin_py = repo_root / "plugins" / "cli" / "plugin.py"
    assert cli_plugin_py.exists()
    text = cli_plugin_py.read_text(encoding="utf-8")

    # No core dispatch.
    assert 'command == "import"' not in text

    # plugin.yaml declares cli_commands (import).
    import_plugin_yaml = repo_root / "plugins" / "import" / "plugin.yaml"
    assert import_plugin_yaml.exists()
    yml = import_plugin_yaml.read_text(encoding="utf-8")
    assert "cli_commands" in yml
    assert "- import" in yml

    # Help lists import under plugin commands.
    import_plugin_dir = repo_root / "plugins" / "import"
    help_text = CLIPlugin._build_help_for_tests([import_plugin_dir])
    assert "Plugin commands:" in help_text
    assert "import" in help_text
