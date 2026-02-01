"""Comprehensive tests for Web Server plugin.

Tests all endpoints, functionality, and edge cases.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

import pytest

# Check if FastAPI is available
try:
    from fastapi.testclient import TestClient
    from plugins.web_server.plugin import WebServerPlugin

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    TestClient = None
    WebServerPlugin = None


pytestmark = pytest.mark.skipif(not HAS_FASTAPI, reason="FastAPI not installed")


# ═══════════════════════════════════════════
#  FIXTURES
# ═══════════════════════════════════════════


@pytest.fixture
def temp_upload_dir(tmp_path):
    """Create temporary upload directory."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    return upload_dir


@pytest.fixture
def web_plugin(temp_upload_dir):
    """Create WebServerPlugin instance for testing."""
    config = {
        "host": "127.0.0.1",
        "port": 48888,
        "upload_dir": str(temp_upload_dir),
    }
    plugin = WebServerPlugin(config=config)
    return plugin


@pytest.fixture
def test_client(web_plugin):
    """Create FastAPI test client."""
    return TestClient(web_plugin.app)


@pytest.fixture
def mock_plugin_loader():
    """Create mock PluginLoader."""
    loader = Mock()
    loader.list_plugins.return_value = ["cli", "tui", "audio_processor"]

    # Mock manifests
    manifest_cli = Mock()
    manifest_cli.name = "cli"
    manifest_cli.version = "1.0.0"
    manifest_cli.description = "Command-line interface"
    manifest_cli.author = "AudioMason Team"
    manifest_cli.interfaces = ["ui_interface"]

    manifest_tui = Mock()
    manifest_tui.name = "tui"
    manifest_tui.version = "1.0.0"
    manifest_tui.description = "Text user interface"
    manifest_tui.author = "AudioMason Team"
    manifest_tui.interfaces = ["ui_interface"]

    loader.get_manifest.side_effect = lambda name: {
        "cli": manifest_cli,
        "tui": manifest_tui,
        "audio_processor": None,
    }.get(name)

    return loader


# ═══════════════════════════════════════════
#  INITIALIZATION TESTS
# ═══════════════════════════════════════════


class TestWebServerInit:
    """Test WebServerPlugin initialization."""

    def test_init_with_default_config(self, tmp_path):
        """Test initialization with default configuration."""
        plugin = WebServerPlugin()

        assert plugin.host == "0.0.0.0"
        assert plugin.port > 45000  # Random port
        assert plugin.reload is False
        assert plugin.verbosity == 1  # NORMAL
        assert len(plugin.contexts) == 0
        assert len(plugin.websocket_clients) == 0

    def test_init_with_custom_config(self, temp_upload_dir):
        """Test initialization with custom configuration."""
        config = {
            "host": "localhost",
            "port": 9999,
            "reload": True,
            "upload_dir": str(temp_upload_dir),
        }
        plugin = WebServerPlugin(config=config)

        assert plugin.host == "localhost"
        assert plugin.port == 9999
        assert plugin.reload is True
        assert plugin.upload_dir == temp_upload_dir

    def test_init_creates_upload_dir(self, tmp_path):
        """Test that upload directory is created if it doesn't exist."""
        upload_dir = tmp_path / "new_uploads"
        config = {"upload_dir": str(upload_dir)}

        assert not upload_dir.exists()
        plugin = WebServerPlugin(config=config)
        assert upload_dir.exists()

    def test_init_without_fastapi(self):
        """Test initialization fails gracefully without FastAPI."""
        with patch("plugins.web_server.plugin.HAS_FASTAPI", False):
            with pytest.raises(ImportError, match="FastAPI not installed"):
                WebServerPlugin()

    def test_random_port_in_valid_range(self):
        """Test that random port is > 45000."""
        plugin = WebServerPlugin()
        assert plugin.port > 45000
        assert plugin.port <= 65535


# ═══════════════════════════════════════════
#  WEB UI ENDPOINT TESTS
# ═══════════════════════════════════════════


class TestWebUIEndpoints:
    """Test HTML/Web UI endpoints."""

    def test_index_page(self, test_client):
        """Test index page renders correctly."""
        response = test_client.get("/")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert b"AudioMason" in response.content
        assert b"Dashboard" in response.content

    def test_plugins_page(self, test_client, web_plugin, mock_plugin_loader):
        """Test plugins page renders correctly."""
        web_plugin.plugin_loader = mock_plugin_loader

        response = test_client.get("/plugins")

        assert response.status_code == 200
        assert b"Plugins" in response.content
        assert b"cli" in response.content or b"CLI" in response.content

    def test_config_page(self, test_client):
        """Test config page renders correctly."""
        response = test_client.get("/config")

        assert response.status_code == 200
        assert b"Configuration" in response.content

    def test_jobs_page(self, test_client):
        """Test jobs page renders correctly."""
        response = test_client.get("/jobs")

        assert response.status_code == 200
        assert b"Jobs" in response.content or b"jobs" in response.content

    def test_wizards_page(self, test_client):
        """Test wizards page renders correctly."""
        response = test_client.get("/wizards")

        assert response.status_code == 200
        assert b"Wizards" in response.content or b"wizards" in response.content


# ═══════════════════════════════════════════
#  API ENDPOINT TESTS
# ═══════════════════════════════════════════


class TestAPIEndpoints:
    """Test JSON API endpoints."""

    def test_get_status(self, test_client):
        """Test GET /api/status endpoint."""
        response = test_client.get("/api/status")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "active_jobs" in data
        assert "version" in data
        assert data["status"] == "running"

    def test_get_config(self, test_client):
        """Test GET /api/config endpoint."""
        response = test_client.get("/api/config")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_update_config(self, test_client):
        """Test POST /api/config endpoint."""
        config_data = {
            "target_bitrate": "192k",
            "loudnorm": True,
        }

        response = test_client.post("/api/config", json=config_data)

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["data"] == config_data

    def test_list_plugins_api(self, test_client, web_plugin, mock_plugin_loader):
        """Test GET /api/plugins endpoint."""
        web_plugin.plugin_loader = mock_plugin_loader

        response = test_client.get("/api/plugins")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_wizards_api(self, test_client):
        """Test GET /api/wizards endpoint."""
        response = test_client.get("/api/wizards")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_list_jobs_empty(self, test_client):
        """Test GET /api/jobs with no jobs."""
        response = test_client.get("/api/jobs")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_list_jobs_with_contexts(self, test_client, web_plugin):
        """Test GET /api/jobs with active contexts."""
        from audiomason.core import ProcessingContext, State

        # Add test context
        ctx = ProcessingContext(
            id="test-123",
            source=Path("/test/file.m4b"),
            author="Test Author",
            title="Test Book",
            state=State.PROCESSING,
        )
        web_plugin.contexts[ctx.id] = ctx

        response = test_client.get("/api/jobs")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "test-123"
        assert data[0]["author"] == "Test Author"

    def test_get_job_exists(self, test_client, web_plugin):
        """Test GET /api/jobs/{job_id} with existing job."""
        from audiomason.core import ProcessingContext, State

        ctx = ProcessingContext(
            id="test-456",
            source=Path("/test/file.m4b"),
            author="Test Author",
            title="Test Book",
            state=State.PROCESSING,
        )
        web_plugin.contexts[ctx.id] = ctx

        response = test_client.get(f"/api/jobs/{ctx.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test-456"
        assert data["author"] == "Test Author"

    def test_get_job_not_found(self, test_client):
        """Test GET /api/jobs/{job_id} with non-existent job."""
        response = test_client.get("/api/jobs/nonexistent-id")

        assert response.status_code == 404
        data = response.json()
        assert "error" in data


# ═══════════════════════════════════════════
#  FILE UPLOAD TESTS
# ═══════════════════════════════════════════


class TestFileUpload:
    """Test file upload functionality."""

    def test_upload_file_success(self, test_client, temp_upload_dir):
        """Test successful file upload."""
        test_content = b"Test audio file content"
        files = {"file": ("test.m4b", test_content, "audio/m4b")}

        response = test_client.post("/api/upload", files=files)

        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "test.m4b"
        assert data["size"] == len(test_content)

        # Verify file was saved
        uploaded_file = temp_upload_dir / "test.m4b"
        assert uploaded_file.exists()
        assert uploaded_file.read_bytes() == test_content

    def test_upload_file_large(self, test_client, temp_upload_dir):
        """Test uploading large file."""
        # 10 MB test file
        test_content = b"X" * (10 * 1024 * 1024)
        files = {"file": ("large.m4b", test_content, "audio/m4b")}

        response = test_client.post("/api/upload", files=files)

        assert response.status_code == 200
        data = response.json()
        assert data["size"] == len(test_content)


# ═══════════════════════════════════════════
#  PROCESSING TESTS
# ═══════════════════════════════════════════


class TestProcessing:
    """Test audio processing functionality."""

    def test_start_processing_success(self, test_client, temp_upload_dir):
        """Test starting processing job successfully."""
        # Create test file
        test_file = temp_upload_dir / "test.m4b"
        test_file.write_text("test content")

        form_data = {
            "filename": "test.m4b",
            "author": "Test Author",
            "title": "Test Book",
            "year": 2024,
            "bitrate": "128k",
            "loudnorm": False,
            "split_chapters": False,
            "pipeline": "standard",
        }

        response = test_client.post("/api/process", data=form_data)

        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert "message" in data

    def test_start_processing_file_not_found(self, test_client):
        """Test starting processing with non-existent file."""
        form_data = {
            "filename": "nonexistent.m4b",
            "author": "Test Author",
            "title": "Test Book",
        }

        response = test_client.post("/api/process", data=form_data)

        assert response.status_code == 404
        data = response.json()
        assert "error" in data

    def test_cancel_job_success(self, test_client, web_plugin):
        """Test canceling an active job."""
        from audiomason.core import ProcessingContext, State

        ctx = ProcessingContext(
            id="cancel-test",
            source=Path("/test/file.m4b"),
            author="Test",
            title="Test",
            state=State.PROCESSING,
        )
        web_plugin.contexts[ctx.id] = ctx

        response = test_client.delete(f"/api/jobs/{ctx.id}")

        assert response.status_code == 200
        assert web_plugin.contexts[ctx.id].state == State.INTERRUPTED

    def test_cancel_job_not_found(self, test_client):
        """Test canceling non-existent job."""
        response = test_client.delete("/api/jobs/nonexistent")

        assert response.status_code == 404
        data = response.json()
        assert "error" in data


# ═══════════════════════════════════════════
#  CHECKPOINT TESTS
# ═══════════════════════════════════════════


class TestCheckpoints:
    """Test checkpoint functionality."""

    @patch("plugins.web_server.plugin.CheckpointManager")
    def test_list_checkpoints(self, mock_manager_class, test_client):
        """Test listing checkpoints."""
        mock_manager = Mock()
        mock_manager.list_checkpoints.return_value = [
            {"id": "cp1", "timestamp": "2024-01-01"},
            {"id": "cp2", "timestamp": "2024-01-02"},
        ]
        mock_manager_class.return_value = mock_manager

        response = test_client.get("/api/checkpoints")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == "cp1"

    @patch("plugins.web_server.plugin.CheckpointManager")
    def test_resume_checkpoint_success(self, mock_manager_class, test_client):
        """Test resuming from checkpoint."""
        from audiomason.core import ProcessingContext, State

        mock_manager = Mock()
        ctx = ProcessingContext(
            id="resumed-123",
            source=Path("/test/file.m4b"),
            author="Test",
            title="Test",
            state=State.PROCESSING,
        )
        mock_manager.load_checkpoint.return_value = ctx
        mock_manager_class.return_value = mock_manager

        response = test_client.post("/api/checkpoints/cp1/resume")

        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data

    @patch("plugins.web_server.plugin.CheckpointManager")
    def test_resume_checkpoint_error(self, mock_manager_class, test_client):
        """Test resuming from invalid checkpoint."""
        mock_manager = Mock()
        mock_manager.load_checkpoint.side_effect = Exception("Invalid checkpoint")
        mock_manager_class.return_value = mock_manager

        response = test_client.post("/api/checkpoints/invalid/resume")

        assert response.status_code == 400
        data = response.json()
        assert "error" in data


# ═══════════════════════════════════════════
#  INTERNAL METHOD TESTS
# ═══════════════════════════════════════════


class TestInternalMethods:
    """Test internal helper methods."""

    @pytest.mark.asyncio
    async def test_get_system_status(self, web_plugin):
        """Test _get_system_status method."""
        status = await web_plugin._get_system_status()

        assert "status" in status
        assert "version" in status
        assert "active_jobs" in status
        assert status["status"] == "running"

    @pytest.mark.asyncio
    async def test_get_plugins_list_no_loader(self, web_plugin):
        """Test _get_plugins_list without loader."""
        plugins = await web_plugin._get_plugins_list()
        assert isinstance(plugins, list)
        assert len(plugins) == 0

    @pytest.mark.asyncio
    async def test_get_plugins_list_with_loader(self, web_plugin, mock_plugin_loader):
        """Test _get_plugins_list with loader."""
        web_plugin.plugin_loader = mock_plugin_loader

        plugins = await web_plugin._get_plugins_list()

        assert isinstance(plugins, list)
        assert len(plugins) > 0
        assert plugins[0]["name"] in ["cli", "tui"]

    @pytest.mark.asyncio
    async def test_get_config_dict(self, web_plugin):
        """Test _get_config_dict method."""
        config = await web_plugin._get_config_dict()

        assert isinstance(config, dict)

    @pytest.mark.asyncio
    async def test_get_jobs_list_empty(self, web_plugin):
        """Test _get_jobs_list with no jobs."""
        jobs = await web_plugin._get_jobs_list()

        assert isinstance(jobs, list)
        assert len(jobs) == 0

    @pytest.mark.asyncio
    async def test_get_jobs_list_with_contexts(self, web_plugin):
        """Test _get_jobs_list with contexts."""
        from audiomason.core import ProcessingContext, State

        ctx = ProcessingContext(
            id="test-789",
            source=Path("/test/file.m4b"),
            author="Author",
            title="Title",
            state=State.PROCESSING,
        )
        web_plugin.contexts[ctx.id] = ctx

        jobs = await web_plugin._get_jobs_list()

        assert len(jobs) == 1
        assert jobs[0]["id"] == "test-789"


# ═══════════════════════════════════════════
#  VERBOSITY TESTS
# ═══════════════════════════════════════════


class TestVerbosity:
    """Test verbosity level handling."""

    def test_default_verbosity(self, web_plugin):
        """Test default verbosity level."""
        from plugins.web_server.plugin import VerbosityLevel

        assert web_plugin.verbosity == VerbosityLevel.NORMAL

    def test_set_verbosity_quiet(self, temp_upload_dir):
        """Test setting verbosity to QUIET."""
        from plugins.web_server.plugin import VerbosityLevel

        plugin = WebServerPlugin(config={"upload_dir": str(temp_upload_dir)})
        plugin.verbosity = VerbosityLevel.QUIET

        assert plugin.verbosity == VerbosityLevel.QUIET

    def test_set_verbosity_debug(self, temp_upload_dir):
        """Test setting verbosity to DEBUG."""
        from plugins.web_server.plugin import VerbosityLevel

        plugin = WebServerPlugin(config={"upload_dir": str(temp_upload_dir)})
        plugin.verbosity = VerbosityLevel.DEBUG

        assert plugin.verbosity == VerbosityLevel.DEBUG


# ═══════════════════════════════════════════
#  WEBSOCKET TESTS
# ═══════════════════════════════════════════


class TestWebSocket:
    """Test WebSocket functionality."""

    @pytest.mark.asyncio
    async def test_broadcast_update_no_clients(self, web_plugin):
        """Test broadcast with no connected clients."""
        from audiomason.core import ProcessingContext, State

        ctx = ProcessingContext(
            id="ws-test",
            source=Path("/test/file.m4b"),
            author="Test",
            title="Test",
            state=State.PROCESSING,
        )
        web_plugin.contexts[ctx.id] = ctx

        # Should not raise error
        await web_plugin._broadcast_update(ctx.id, "complete")

    @pytest.mark.asyncio
    async def test_broadcast_update_with_clients(self, web_plugin):
        """Test broadcast with connected clients."""
        from audiomason.core import ProcessingContext, State

        ctx = ProcessingContext(
            id="ws-test-2",
            source=Path("/test/file.m4b"),
            author="Test",
            title="Test",
            state=State.PROCESSING,
        )
        web_plugin.contexts[ctx.id] = ctx

        # Mock WebSocket client
        mock_client = AsyncMock()
        web_plugin.websocket_clients.append(mock_client)

        await web_plugin._broadcast_update(ctx.id, "complete")

        # Verify client received message
        mock_client.send_json.assert_called_once()
        call_args = mock_client.send_json.call_args[0][0]
        assert call_args["type"] == "job_update"
        assert call_args["job_id"] == "ws-test-2"


# ═══════════════════════════════════════════
#  EDGE CASES & ERROR HANDLING
# ═══════════════════════════════════════════


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_invalid_route(self, test_client):
        """Test accessing non-existent route."""
        response = test_client.get("/nonexistent")
        assert response.status_code == 404

    def test_upload_without_file(self, test_client):
        """Test upload endpoint without file."""
        response = test_client.post("/api/upload", files={})
        assert response.status_code == 422  # Validation error

    def test_process_without_required_fields(self, test_client):
        """Test process endpoint without required fields."""
        response = test_client.post("/api/process", data={})
        assert response.status_code == 422  # Validation error

    def test_get_job_invalid_id(self, test_client):
        """Test get job with various invalid IDs."""
        invalid_ids = ["", "   ", "null", "undefined", "../../../etc/passwd"]

        for job_id in invalid_ids:
            response = test_client.get(f"/api/jobs/{job_id}")
            assert response.status_code in [404, 422]
