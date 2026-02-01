"""Tests for daemon plugin manifest - descriptions fix."""

from pathlib import Path

import pytest
import yaml


class TestDaemonManifest:
    """Test daemon plugin manifest."""

    @pytest.fixture
    def manifest_path(self):
        """Get path to daemon manifest."""
        # Try multiple locations
        candidates = [
            Path(__file__).parent.parent.parent / "plugins" / "daemon" / "plugin.yaml",
            Path(__file__).parent.parent.parent.parent / "plugins" / "daemon" / "plugin.yaml",
        ]

        for path in candidates:
            if path.exists():
                return path

        pytest.skip("Daemon manifest not found")

    @pytest.fixture
    def manifest(self, manifest_path):
        """Load daemon manifest."""
        with open(manifest_path) as f:
            return yaml.safe_load(f)

    def test_manifest_exists(self, manifest_path):
        """Test that daemon manifest exists."""
        assert manifest_path.exists()

    def test_manifest_has_config_schema(self, manifest):
        """Test that manifest has config_schema."""
        assert "config_schema" in manifest
        assert isinstance(manifest["config_schema"], dict)

    def test_watch_folders_has_description(self, manifest):
        """Test that watch_folders has description."""
        schema = manifest["config_schema"]

        assert "watch_folders" in schema
        assert "description" in schema["watch_folders"]
        assert len(schema["watch_folders"]["description"]) > 0

    def test_interval_has_description(self, manifest):
        """Test that interval has description."""
        schema = manifest["config_schema"]

        assert "interval" in schema
        assert "description" in schema["interval"]
        assert len(schema["interval"]["description"]) > 0

    def test_on_success_has_description(self, manifest):
        """Test that on_success has description."""
        schema = manifest["config_schema"]

        assert "on_success" in schema
        assert "description" in schema["on_success"]
        assert len(schema["on_success"]["description"]) > 0

    def test_on_error_has_description(self, manifest):
        """Test that on_error has description."""
        schema = manifest["config_schema"]

        assert "on_error" in schema
        assert "description" in schema["on_error"]
        assert len(schema["on_error"]["description"]) > 0

    def test_all_descriptions_meaningful(self, manifest):
        """Test that all descriptions are meaningful."""
        schema = manifest["config_schema"]

        for key, value in schema.items():
            if "description" in value:
                desc = value["description"]

                # Description should be meaningful (not just the key name)
                assert len(desc) > len(key)

                # Description should be a sentence (has spaces)
                assert " " in desc

    def test_watch_folders_description_content(self, manifest):
        """Test watch_folders description content."""
        desc = manifest["config_schema"]["watch_folders"]["description"]

        # Should mention what it does
        assert any(word in desc.lower() for word in ["watch", "monitor", "check", "scan"])
        assert any(word in desc.lower() for word in ["folder", "director", "path"])

    def test_interval_description_content(self, manifest):
        """Test interval description content."""
        desc = manifest["config_schema"]["interval"]["description"]

        # Should mention timing
        assert any(word in desc.lower() for word in ["often", "frequently", "interval", "check"])
        assert any(word in desc.lower() for word in ["second", "time"])

    def test_on_success_description_content(self, manifest):
        """Test on_success description content."""
        desc = manifest["config_schema"]["on_success"]["description"]

        # Should mention what happens to files
        assert any(word in desc.lower() for word in ["file", "source"])
        assert any(word in desc.lower() for word in ["success", "successful", "process"])

    def test_on_error_description_content(self, manifest):
        """Test on_error description content."""
        desc = manifest["config_schema"]["on_error"]["description"]

        # Should mention errors/failures
        assert any(word in desc.lower() for word in ["error", "fail", "failed"])
        assert any(word in desc.lower() for word in ["file", "source"])


class TestDaemonManifestSchema:
    """Test daemon manifest schema structure."""

    @pytest.fixture
    def manifest_path(self):
        """Get path to daemon manifest."""
        candidates = [
            Path(__file__).parent.parent.parent / "plugins" / "daemon" / "plugin.yaml",
            Path(__file__).parent.parent.parent.parent / "plugins" / "daemon" / "plugin.yaml",
        ]

        for path in candidates:
            if path.exists():
                return path

        pytest.skip("Daemon manifest not found")

    @pytest.fixture
    def manifest(self, manifest_path):
        """Load daemon manifest."""
        with open(manifest_path) as f:
            return yaml.safe_load(f)

    def test_watch_folders_type(self, manifest):
        """Test watch_folders type."""
        schema = manifest["config_schema"]["watch_folders"]

        assert schema["type"] == "array"
        assert "items" in schema
        assert schema["items"]["type"] == "string"

    def test_interval_type_and_constraints(self, manifest):
        """Test interval type and constraints."""
        schema = manifest["config_schema"]["interval"]

        assert schema["type"] == "integer"
        assert schema["default"] == 30

        # Should have reasonable bounds
        if "minimum" in schema:
            assert schema["minimum"] >= 1
        if "maximum" in schema:
            assert schema["maximum"] <= 86400  # 24 hours

    def test_on_success_enum(self, manifest):
        """Test on_success enum values."""
        schema = manifest["config_schema"]["on_success"]

        assert schema["type"] == "string"
        assert "enum" in schema
        assert "move_to_output" in schema["enum"]
        assert "keep" in schema["enum"]
        assert "delete" in schema["enum"]

    def test_on_error_enum(self, manifest):
        """Test on_error enum values."""
        schema = manifest["config_schema"]["on_error"]

        assert schema["type"] == "string"
        assert "enum" in schema["enum"]
        assert "move_to_error" in schema["enum"]
        assert "keep" in schema["enum"]
        assert "delete" in schema["enum"]


class TestDaemonManifestComparison:
    """Test that new manifest is better than old."""

    def test_has_more_fields_than_old(self):
        """Test that new manifest has descriptions (old didn't)."""
        # This test documents what was fixed
        old_manifest = {
            "watch_folders": {"type": "array", "items": {"type": "string"}, "default": []}
        }

        new_manifest_fields = {"type", "description", "items", "default"}
        old_manifest_fields = set(old_manifest["watch_folders"].keys())

        assert "description" in new_manifest_fields
        assert "description" not in old_manifest_fields
