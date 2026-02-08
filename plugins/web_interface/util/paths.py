from __future__ import annotations

import os
from pathlib import Path


def user_config_dir() -> Path:
    return Path(os.path.expanduser("~/.config/audiomason"))


def am_config_path() -> Path:
    return user_config_dir() / "config.yaml"


def ui_overrides_path() -> Path:
    return user_config_dir() / "web_interface_ui.json"


def plugins_root(repo_root: Path) -> Path:
    # Built-in plugins live in the repository. This path is read-only for the web UI.
    return repo_root / "plugins"


def stage_dir_from_config(inbox_dir: str | None, repo_root: Path) -> Path:
    # Stage dir must never default into the repository.
    if os.environ.get("WEB_INTERFACE_STAGE_DIR"):
        return Path(os.environ["WEB_INTERFACE_STAGE_DIR"])
    if inbox_dir:
        return Path(inbox_dir) / "stage"
    return Path(os.path.expanduser("~/.audiomason/stage"))


def log_path_default() -> Path | None:
    p = os.environ.get("WEB_INTERFACE_LOG_PATH")
    return Path(p) if p else None


def debug_enabled() -> bool:
    v = os.environ.get("WEB_INTERFACE_DEBUG")
    if not v:
        return False
    return v.strip().lower() not in {"0", "false", "no", "off"}
