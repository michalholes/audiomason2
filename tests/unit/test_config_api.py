"""Tests for Config API - input_dir fix."""

import tempfile
from pathlib import Path

import pytest

from audiomason.api.config import ConfigAPI


class TestConfigAPIDefaults:
    """Test config API default values."""

    def test_input_dir_in_defaults(self):
        """Test that input_dir is in default config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            api = ConfigAPI(config_file)

            config = api.get_config()

            assert "input_dir" in config
            assert isinstance(config["input_dir"], str)
            assert "Audiobooks" in config["input_dir"]
            assert "input" in config["input_dir"]

    def test_output_dir_in_defaults(self):
        """Test that output_dir is still in default config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            api = ConfigAPI(config_file)

            config = api.get_config()

            assert "output_dir" in config
            assert isinstance(config["output_dir"], str)
            assert "Audiobooks" in config["output_dir"]
            assert "output" in config["output_dir"]


class TestConfigAPISchema:
    """Test config API schema."""

    def test_input_dir_in_schema(self):
        """Test that input_dir is in config schema."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            api = ConfigAPI(config_file)

            schema = api.get_config_schema()

            assert "input_dir" in schema
            assert schema["input_dir"]["type"] == "string"
            assert "label" in schema["input_dir"]
            assert "description" in schema["input_dir"]
            assert "default" in schema["input_dir"]

    def test_input_dir_schema_details(self):
        """Test input_dir schema details."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "casa.yaml"
            api = ConfigAPI(config_file)

            schema = api.get_config_schema()
            input_schema = schema["input_dir"]

            assert input_schema["label"] == "Input Directory"
            assert "looks for files" in input_schema["description"].lower()
            assert "Audiobooks" in input_schema["default"]
            assert "input" in input_schema["default"]

    def test_output_dir_schema_still_present(self):
        """Test that output_dir schema is still present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            api = ConfigAPI(config_file)

            schema = api.get_config_schema()

            assert "output_dir" in schema
            assert schema["output_dir"]["type"] == "string"


class TestConfigAPIPersistence:
    """Test config persistence with input_dir."""

    def test_input_dir_persists(self):
        """Test that input_dir is saved and loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"

            # Create API and update input_dir
            api1 = ConfigAPI(config_file)
            api1.update_config({"input_dir": "/custom/input"})

            # Create new API instance (should load from file)
            api2 = ConfigAPI(config_file)
            config = api2.get_config()

            assert config["input_dir"] == "/custom/input"

    def test_default_dirs_different(self):
        """Test that input_dir and output_dir defaults are different."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            api = ConfigAPI(config_file)

            config = api.get_config()

            assert config["input_dir"] != config["output_dir"]
            assert "input" in config["input_dir"]
            assert "output" in config["output_dir"]


class TestConfigAPIUpdate:
    """Test config update with input_dir."""

    def test_update_input_dir(self):
        """Test updating input_dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            api = ConfigAPI(config_file)

            result = api.update_config({"input_dir": "/new/input"})

            assert "message" in result

            config = api.get_config()
            assert config["input_dir"] == "/new/input"

    def test_update_multiple_dirs(self):
        """Test updating both input and output dirs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            api = ConfigAPI(config_file)

            api.update_config({"input_dir": "/custom/in", "output_dir": "/custom/out"})

            config = api.get_config()
            assert config["input_dir"] == "/custom/in"
            assert config["output_dir"] == "/custom/out"


class TestConfigAPIReset:
    """Test config reset with input_dir."""

    def test_reset_restores_input_dir(self):
        """Test that reset restores default input_dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            api = ConfigAPI(config_file)

            # Change input_dir
            api.update_config({"input_dir": "/custom"})

            # Reset
            api.reset_config()

            # Check default is restored
            config = api.get_config()
            assert "Audiobooks" in config["input_dir"]
            assert "input" in config["input_dir"]


class TestBackwardsCompatibility:
    """Test that existing configs without input_dir still work."""

    def test_missing_input_dir_handled(self):
        """Test loading config without input_dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"

            # Manually create old-style config
            import yaml

            old_config = {"output_dir": "/old/output", "bitrate": "192k"}
            with open(config_file, "w") as f:
                yaml.safe_dump(old_config, f)

            # Load with new API
            api = ConfigAPI(config_file)
            config = api.get_config()

            # Should have output_dir from file
            assert config["output_dir"] == "/old/output"

            # Should have default input_dir (not crash)
            assert "input_dir" in config
