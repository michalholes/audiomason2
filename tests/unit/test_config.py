"""Unit tests for core.config module."""

import pytest
from pathlib import Path

from audiomason.core.config import ConfigResolver
from audiomason.core.errors import ConfigError


class TestConfigResolver:
    """Tests for ConfigResolver."""

    def test_cli_priority(self, tmp_path):
        """Test that CLI args have highest priority."""
        user_config = tmp_path / "config.yaml"
        user_config.write_text("bitrate: 128k\n")

        resolver = ConfigResolver(
            cli_args={"bitrate": "320k"},
            user_config_path=user_config,
        )

        value, source = resolver.resolve("bitrate")
        assert value == "320k"
        assert source == "cli"

    def test_env_priority(self, tmp_path, monkeypatch):
        """Test that ENV overrides config files."""
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

    def test_user_config_priority(self, tmp_path):
        """Test that user config overrides system config."""
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

    def test_defaults(self, tmp_path):
        """Test that defaults are used when nothing else provides value."""
        resolver = ConfigResolver(
            cli_args={},
            user_config_path=tmp_path / "nonexistent.yaml",
            system_config_path=tmp_path / "nonexistent.yaml",
        )

        value, source = resolver.resolve("bitrate")
        assert value == "128k"  # Default
        assert source == "default"

    def test_nested_keys(self, tmp_path):
        """Test nested keys with dot notation."""
        user_config = tmp_path / "config.yaml"
        user_config.write_text(
            """
logging:
  level: debug
  color: true
"""
        )

        resolver = ConfigResolver(
            cli_args={},
            user_config_path=user_config,
        )

        level, source = resolver.resolve("logging.level")
        assert level == "debug"
        assert source == "user_config"

        color, source = resolver.resolve("logging.color")
        assert color is True

    def test_missing_key_raises_error(self, tmp_path):
        """Test that missing key raises ConfigError."""
        resolver = ConfigResolver(
            cli_args={},
            user_config_path=tmp_path / "nonexistent.yaml",
            defaults={},
        )

        with pytest.raises(ConfigError, match="not found"):
            resolver.resolve("nonexistent_key")

    def test_false_values_work(self, tmp_path):
        """Test that False values are handled correctly."""
        resolver = ConfigResolver(
            cli_args={},
            user_config_path=tmp_path / "nonexistent.yaml",
            system_config_path=tmp_path / "nonexistent_system.yaml",
            defaults={"loudnorm": False, "split_chapters": False},
        )

        loudnorm, source = resolver.resolve("loudnorm")
        assert loudnorm is False
        assert source == "default"

    def test_resolve_all(self, tmp_path):
        """Test resolving all keys."""
        resolver = ConfigResolver(
            cli_args={"bitrate": "320k"},
            user_config_path=tmp_path / "nonexistent.yaml",
            system_config_path=tmp_path / "nonexistent_system.yaml",
            defaults={"bitrate": "128k", "loudnorm": False},
        )

        all_config = resolver.resolve_all()

        assert "bitrate" in all_config
        assert all_config["bitrate"].value == "320k"
        assert all_config["bitrate"].source == "cli"

        assert "loudnorm" in all_config
        assert all_config["loudnorm"].value is False
