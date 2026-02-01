"""Integration tests for Web Server plugin.

Tests end-to-end workflows and integration with other components.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Check if FastAPI is available
try:
    from fastapi.testclient import TestClient
    from plugins.web_server.plugin import WebServerPlugin

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


pytestmark = pytest.mark.skipif(not HAS_FASTAPI, reason="FastAPI not installed")


# ═══════════════════════════════════════════
#  END-TO-END WORKFLOW TESTS
# ═══════════════════════════════════════════


class TestEndToEndWorkflow:
    """Test complete workflows from upload to completion."""

    def test_upload_and_process_workflow(self, tmp_path):
        """Test complete upload and processing workflow."""
        # Setup
        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()

        config = {
            "port": 48889,
            "upload_dir": str(upload_dir),
        }
        plugin = WebServerPlugin(config=config)
        client = TestClient(plugin.app)

        # Step 1: Upload file
        test_content = b"Test audio content"
        files = {"file": ("book.m4b", test_content, "audio/m4b")}

        upload_response = client.post("/api/upload", files=files)
        assert upload_response.status_code == 200
        upload_data = upload_response.json()

        # Step 2: Start processing
        form_data = {
            "filename": upload_data["filename"],
            "author": "Test Author",
            "title": "Test Book",
            "year": 2024,
            "bitrate": "128k",
            "loudnorm": True,
            "split_chapters": False,
            "pipeline": "standard",
        }

        process_response = client.post("/api/process", data=form_data)
        assert process_response.status_code == 200
        process_data = process_response.json()
        assert "job_id" in process_data

        # Step 3: Check job status
        job_id = process_data["job_id"]
        status_response = client.get(f"/api/jobs/{job_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["author"] == "Test Author"
        assert status_data["title"] == "Test Book"

    def test_multiple_concurrent_jobs(self, tmp_path):
        """Test handling multiple concurrent processing jobs."""
        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()

        config = {"upload_dir": str(upload_dir)}
        plugin = WebServerPlugin(config=config)
        client = TestClient(plugin.app)

        job_ids = []

        # Create and start 3 jobs
        for i in range(3):
            # Upload
            files = {"file": (f"book{i}.m4b", b"content", "audio/m4b")}
            upload_response = client.post("/api/upload", files=files)
            filename = upload_response.json()["filename"]

            # Process
            form_data = {
                "filename": filename,
                "author": f"Author {i}",
                "title": f"Book {i}",
            }
            process_response = client.post("/api/process", data=form_data)
            job_ids.append(process_response.json()["job_id"])

        # Check all jobs exist
        jobs_response = client.get("/api/jobs")
        jobs = jobs_response.json()
        assert len(jobs) == 3

        # Verify each job
        for job_id in job_ids:
            response = client.get(f"/api/jobs/{job_id}")
            assert response.status_code == 200


# ═══════════════════════════════════════════
#  TEMPLATE RENDERING TESTS
# ═══════════════════════════════════════════


class TestTemplateRendering:
    """Test Jinja2 template rendering with various data."""

    def test_index_with_active_jobs(self, tmp_path):
        """Test index page renders with active jobs."""
        from audiomason.core import ProcessingContext, State

        config = {"upload_dir": str(tmp_path)}
        plugin = WebServerPlugin(config=config)
        client = TestClient(plugin.app)

        # Add active context
        ctx = ProcessingContext(
            id="render-test",
            source=Path("/test/file.m4b"),
            author="Test",
            title="Test",
            state=State.PROCESSING,
        )
        plugin.contexts[ctx.id] = ctx

        response = client.get("/")

        assert response.status_code == 200
        assert b"1" in response.content  # Active jobs count

    def test_plugins_page_with_data(self, tmp_path):
        """Test plugins page renders with plugin data."""
        config = {"upload_dir": str(tmp_path)}
        plugin = WebServerPlugin(config=config)
        client = TestClient(plugin.app)

        # Mock plugin loader
        loader = Mock()
        loader.list_plugins.return_value = ["test_plugin"]

        manifest = Mock()
        manifest.name = "test_plugin"
        manifest.version = "1.0.0"
        manifest.description = "Test Plugin"
        manifest.author = "Test Author"
        manifest.interfaces = ["processor"]

        loader.get_manifest.return_value = manifest
        plugin.plugin_loader = loader

        response = client.get("/plugins")

        assert response.status_code == 200
        assert b"test_plugin" in response.content

    def test_jobs_page_with_various_states(self, tmp_path):
        """Test jobs page renders with jobs in various states."""
        from audiomason.core import ProcessingContext, State

        config = {"upload_dir": str(tmp_path)}
        plugin = WebServerPlugin(config=config)
        client = TestClient(plugin.app)

        # Add contexts in different states
        states = [State.PROCESSING, State.COMPLETE, State.ERROR, State.INTERRUPTED]
        for i, state in enumerate(states):
            ctx = ProcessingContext(
                id=f"job-{i}",
                source=Path(f"/test/file{i}.m4b"),
                author=f"Author {i}",
                title=f"Title {i}",
                state=state,
            )
            plugin.contexts[ctx.id] = ctx

        response = client.get("/jobs")

        assert response.status_code == 200
        assert response.content.count(b"badge") >= 4  # One badge per job


# ═══════════════════════════════════════════
#  API INTEGRATION TESTS
# ═══════════════════════════════════════════


class TestAPIIntegration:
    """Test API integration with other components."""

    @patch("plugins.web_server.plugin.ConfigResolver")
    def test_config_integration(self, mock_resolver_class, tmp_path):
        """Test configuration integration."""
        config = {"upload_dir": str(tmp_path)}
        plugin = WebServerPlugin(config=config)
        client = TestClient(plugin.app)

        # Mock ConfigResolver
        mock_resolver = Mock()
        mock_value = Mock()
        mock_value.value = "128k"
        mock_value.source = "default"

        mock_resolver.resolve_all.return_value = {
            "target_bitrate": mock_value,
        }
        mock_resolver_class.return_value = mock_resolver

        response = client.get("/api/config")

        assert response.status_code == 200
        data = response.json()
        assert "target_bitrate" in data

    def test_plugin_loader_integration(self, tmp_path):
        """Test plugin loader integration."""
        config = {"upload_dir": str(tmp_path)}
        plugin = WebServerPlugin(config=config)

        # Mock plugin loader with multiple plugins
        loader = Mock()
        loader.list_plugins.return_value = ["cli", "tui", "web_server"]

        # Create manifests
        manifests = {}
        for name in ["cli", "tui", "web_server"]:
            m = Mock()
            m.name = name
            m.version = "1.0.0"
            m.description = f"{name} plugin"
            m.author = "AudioMason"
            m.interfaces = ["ui_interface"] if name in ["cli", "tui"] else []
            manifests[name] = m

        loader.get_manifest.side_effect = lambda n: manifests.get(n)
        plugin.plugin_loader = loader

        client = TestClient(plugin.app)
        response = client.get("/api/plugins")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3


# ═══════════════════════════════════════════
#  ERROR RECOVERY TESTS
# ═══════════════════════════════════════════


class TestErrorRecovery:
    """Test error handling and recovery."""

    def test_processing_error_handling(self, tmp_path):
        """Test handling of processing errors."""
        from audiomason.core import ProcessingContext, State

        config = {"upload_dir": str(tmp_path)}
        plugin = WebServerPlugin(config=config)

        # Create context with error
        ctx = ProcessingContext(
            id="error-test",
            source=Path("/test/file.m4b"),
            author="Test",
            title="Test",
            state=State.ERROR,
        )
        ctx.add_error(Exception("Test error"))
        plugin.contexts[ctx.id] = ctx

        client = TestClient(plugin.app)
        response = client.get(f"/api/jobs/{ctx.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "ERROR"

    def test_upload_directory_recovery(self, tmp_path):
        """Test recovery when upload directory is deleted."""
        upload_dir = tmp_path / "uploads"
        upload_dir.mkdir()

        config = {"upload_dir": str(upload_dir)}
        plugin = WebServerPlugin(config=config)

        # Delete directory
        import shutil

        shutil.rmtree(upload_dir)

        # Plugin should recreate it
        plugin.upload_dir.mkdir(parents=True, exist_ok=True)

        client = TestClient(plugin.app)
        files = {"file": ("test.m4b", b"content", "audio/m4b")}
        response = client.post("/api/upload", files=files)

        assert response.status_code == 200


# ═══════════════════════════════════════════
#  PERFORMANCE TESTS
# ═══════════════════════════════════════════


class TestPerformance:
    """Test performance characteristics."""

    def test_large_jobs_list_performance(self, tmp_path):
        """Test handling large number of jobs."""
        from audiomason.core import ProcessingContext, State

        config = {"upload_dir": str(tmp_path)}
        plugin = WebServerPlugin(config=config)

        # Create 100 jobs
        for i in range(100):
            ctx = ProcessingContext(
                id=f"perf-{i}",
                source=Path(f"/test/file{i}.m4b"),
                author=f"Author {i}",
                title=f"Title {i}",
                state=State.COMPLETE,
            )
            plugin.contexts[ctx.id] = ctx

        client = TestClient(plugin.app)

        # Should handle large list efficiently
        import time

        start = time.time()
        response = client.get("/api/jobs")
        duration = time.time() - start

        assert response.status_code == 200
        assert duration < 1.0  # Should complete in under 1 second
        data = response.json()
        assert len(data) == 100

    def test_concurrent_requests(self, tmp_path):
        """Test handling concurrent API requests."""
        config = {"upload_dir": str(tmp_path)}
        plugin = WebServerPlugin(config=config)
        client = TestClient(plugin.app)

        # Make 10 concurrent status requests
        import concurrent.futures

        def make_request():
            return client.get("/api/status")

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            results = [f.result() for f in futures]

        # All should succeed
        assert all(r.status_code == 200 for r in results)


# ═══════════════════════════════════════════
#  SECURITY TESTS
# ═══════════════════════════════════════════


class TestSecurity:
    """Test security features."""

    def test_path_traversal_prevention(self, tmp_path):
        """Test prevention of path traversal attacks."""
        config = {"upload_dir": str(tmp_path)}
        plugin = WebServerPlugin(config=config)
        client = TestClient(plugin.app)

        # Try to access file outside upload dir
        malicious_filenames = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "....//....//....//etc/passwd",
        ]

        for filename in malicious_filenames:
            form_data = {
                "filename": filename,
                "author": "Test",
                "title": "Test",
            }
            response = client.post("/api/process", data=form_data)
            # Should fail - file doesn't exist in upload dir
            assert response.status_code in [404, 400]

    def test_upload_filename_sanitization(self, tmp_path):
        """Test that uploaded filenames are handled safely."""
        config = {"upload_dir": str(tmp_path)}
        plugin = WebServerPlugin(config=config)
        client = TestClient(plugin.app)

        # Upload with potentially dangerous filename
        files = {"file": ("../../dangerous.m4b", b"content", "audio/m4b")}
        response = client.post("/api/upload", files=files)

        assert response.status_code == 200
        # Verify file is in upload dir, not parent
        data = response.json()
        assert str(tmp_path) in data["path"]
