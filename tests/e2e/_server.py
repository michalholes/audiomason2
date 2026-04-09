from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any

import uvicorn

from audiomason.core.loader import PluginLoader


def _bootstrap_paths() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    repo_root_str = str(repo_root)
    src_root_str = str(repo_root / "src")
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)
    if src_root_str not in sys.path:
        sys.path.insert(0, src_root_str)
    return repo_root


def _load_web_app(*, repo_root: Path, verbosity: int) -> Any:
    plugins_dir = repo_root / "plugins"
    loader = PluginLoader(builtin_plugins_dir=plugins_dir)

    cmd_plugin = importlib.import_module("plugins.cmd_interface.plugin")
    web_core = importlib.import_module("plugins.web_interface.core")

    cmd_plugin.preload_supported_web_plugins(loader=loader, plugins_dir=plugins_dir)
    return web_core.WebInterfacePlugin().create_app(
        plugin_loader=loader,
        verbosity=verbosity,
    )


def main() -> None:
    repo_root = _bootstrap_paths()

    host = os.getenv("E2E_HOST", "127.0.0.1")
    port = int(os.getenv("E2E_PORT", "8081"))
    verbosity = int(os.getenv("E2E_WEB_VERBOSITY", "0"))

    app = _load_web_app(repo_root=repo_root, verbosity=verbosity)

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="error" if verbosity <= 0 else "info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
