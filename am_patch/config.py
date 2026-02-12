from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from .compat import import_legacy, normalize_config_keys
from .model import CLIArgs, RunnerConfig


def default_shadow_config(repo_root: Path) -> tuple[RunnerConfig, Path]:
    """Return shadow-runner defaults and the default config path."""

    cfg = RunnerConfig(verbosity="verbose", test_mode=False)
    default_path = repo_root / "scripts" / "am_patch" / "am_patch.toml"
    return cfg, default_path


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib

        data = tomllib.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}

        flat: dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(v, dict):
                for kk, vv in v.items():
                    flat[str(kk)] = vv
            else:
                flat[str(k)] = v

        return normalize_config_keys(flat)
    except Exception:
        return {}


def load_shadow_config(
    repo_root: Path,
    cli: CLIArgs,
) -> tuple[RunnerConfig, Path, tuple[str, ...]]:
    """Load config using precedence: CLI overrides > config file > defaults."""

    cfg, default_path = default_shadow_config(repo_root)
    sources: list[str] = ["defaults"]

    cfg_path = Path(cli.config_path) if cli.config_path else default_path
    if not cfg_path.is_absolute():
        cfg_path = repo_root / cfg_path

    file_data: dict[str, Any] = {}
    if cfg_path.exists():
        file_data = _read_toml(cfg_path)
        sources.append(str(cfg_path))

    if isinstance(file_data.get("verbosity"), str):
        v = str(file_data["verbosity"]).strip()
        if v:
            cfg = replace(cfg, verbosity=v)
    if isinstance(file_data.get("test_mode"), bool):
        cfg = replace(cfg, test_mode=bool(file_data["test_mode"]))

    # CLI overrides (highest priority).
    if isinstance(cli.verbosity, str):
        v = cli.verbosity.strip()
        if v:
            cfg = replace(cfg, verbosity=v)
    if cli.test_mode is not None:
        cfg = replace(cfg, test_mode=bool(cli.test_mode))

    if any(
        [
            cli.config_path is not None,
            cli.verbosity is not None,
            cli.test_mode is not None,
        ]
    ):
        sources.append("cli")

    return cfg, cfg_path, tuple(sources)


# -----------------------------------------------------------------------------
# Legacy runner compatibility re-exports
#
# Existing tests and code in this repository import "am_patch.*" expecting the
# authoritative runner implementation under scripts/am_patch/.
# -----------------------------------------------------------------------------

try:
    _legacy_config = import_legacy("config")
    Policy = _legacy_config.Policy
    apply_cli_overrides = _legacy_config.apply_cli_overrides
    build_policy = _legacy_config.build_policy
except Exception:
    # Keep shadow runner usable even if legacy cannot be loaded.
    pass
