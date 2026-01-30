"""Tests for ConfigResolver."""

from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from audiomason.core.config import ConfigResolver
from audiomason.core.errors import ConfigError


def test_cli_has_highest_priority(tmp_path: Path) -> None:
    """CLI args have highest priority."""
    # Create temp config file
    user_config = tmp_path / "config.yaml"
    user_config.write_text("bitrate: 128k\n")

    resolver = ConfigResolver(
        cli_args={"bitrate": "320k"},
        user_config_path=user_config,
    )

    value, source = resolver.resolve("bitrate")
    assert value == "320k"
    assert source == "cli"


def test_env_overrides_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment variables override config files."""
    user_config = tmp_path / "config.yaml"
    user_config.write_text("bitrate: 128k\n")

    monkeypatch.setenv("AUDIOMASON_BITRATE", "256k")

    resolver = ConfigResolver(
        cli_args={},
        user_config_path=user_config,
    )

    value, source = resolver.resolve("bitrate")
    assert value == "256k"
    assert source == "env"


def test_user_config_overrides_system(tmp_path: Path) -> None:
    """User config overrides system config."""
    user_config = tmp_path / "user.yaml"
    user_config.write_text("bitrate: 128k\n")

    system_config = tmp_path / "system.yaml"
    system_config.write_text("bitrate: 96k\n")

    resolver = ConfigResolver(
        cli_args={},
        user_config_path=user_config,
        system_config_path=system_config,
    )

    value, source = resolver.resolve("bitrate")
    assert value == "128k"
    assert source == "user_config"


def test_defaults_used_when_nothing_else(tmp_path: Path) -> None:
    """Defaults are used when no other source provides value."""
    resolver = ConfigResolver(
        cli_args={},
        user_config_path=tmp_path / "nonexistent.yaml",
        system_config_path=tmp_path / "nonexistent.yaml",
    )

    value, source = resolver.resolve("bitrate")
    assert value == "128k"  # Default
    assert source == "default"


def test_nested_keys(tmp_path: Path) -> None:
    """Nested keys work with dot notation."""
    user_config = tmp_path / "config.yaml"
    user_config.write_text("""
logging:
  level: debug
  color: true
""")

    resolver = ConfigResolver(
        cli_args={},
        user_config_path=user_config,
    )

    level, source = resolver.resolve("logging.level")
    assert level == "debug"
    assert source == "user_config"

    color, source = resolver.resolve("logging.color")
    assert color is True
    assert source == "user_config"


def test_missing_key_raises_error(tmp_path: Path) -> None:
    """Missing key raises ConfigError."""
    resolver = ConfigResolver(
        cli_args={},
        user_config_path=tmp_path / "nonexistent.yaml",
        defaults={},  # No defaults
    )

    with pytest.raises(ConfigError, match="not found"):
        resolver.resolve("nonexistent_key")


def test_resolve_all() -> None:
    """Resolve all keys."""
    resolver = ConfigResolver(
        cli_args={"bitrate": "320k"},
        defaults={"bitrate": "128k", "loudnorm": False},
    )

    all_config = resolver.resolve_all()

    assert "bitrate" in all_config
    assert all_config["bitrate"].value == "320k"
    assert all_config["bitrate"].source == "cli"

    assert "loudnorm" in all_config
    assert all_config["loudnorm"].value is False
    assert all_config["loudnorm"].source == "default"
