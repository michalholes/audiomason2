"""AudioMason v2 - Package entry point.

This module enables running the project with:

    python -m audiomason ...

The repository also provides the ./audiomason wrapper script. Tests and some
workflows use the module form, so we provide an equivalent entry point here.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from audiomason.core import PluginLoader


def _find_plugins_dir() -> Path:
    """Find the repository plugins directory.

    Preference order:
    1) Search from current working directory upwards.
    2) Search from this file's location upwards (works for editable installs).
    3) Fallback to ./plugins.
    """

    def _search_up(start: Path) -> Path | None:
        p = start.resolve()
        for _ in range(8):
            cand = p / "plugins"
            if (cand / "cli").exists():
                return cand
            if p.parent == p:
                break
            p = p.parent
        return None

    found = _search_up(Path.cwd())
    if found is not None:
        return found

    found = _search_up(Path(__file__).resolve())
    if found is not None:
        return found

    return Path.cwd() / "plugins"


async def main() -> None:
    """Main entry point."""
    plugins_dir = _find_plugins_dir()
    loader = PluginLoader(builtin_plugins_dir=plugins_dir)

    cli_plugin_dir = plugins_dir / "cli"
    if not cli_plugin_dir.exists():
        print("Error: CLI plugin not found")
        print(f"Expected: {cli_plugin_dir}")
        sys.exit(1)

    try:
        cli_plugin = loader.load_plugin(cli_plugin_dir, validate=False)
        await cli_plugin.run()
    except Exception as e:  # pragma: no cover
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
