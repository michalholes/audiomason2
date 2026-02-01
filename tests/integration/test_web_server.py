"""Integration tests for web server plugin."""

import subprocess

import pytest


class TestWebServerRandomPort:
    """Test web server random port assignment."""

    def test_web_server_uses_port_above_45000(self):
        """Test that web server uses random port above 45000 when no port specified."""
        # Start web server without port argument
        result = subprocess.run(
            ["python", "-m", "audiomason", "web"],
            capture_output=True,
            text=True,
            timeout=3,
        )

        # Server will timeout after 3s, but we check it started correctly
        output = result.stdout + result.stderr

        # Check that a port was assigned
        assert "Starting web server" in output or "Web server" in output

        # If port is mentioned, verify it's > 45000
        # Look for patterns like "port 45001" or ":45001"
        import re

        port_matches = re.findall(r"(?:port\s+|:)(\d{5,6})", output)
        if port_matches:
            for port_str in port_matches:
                port = int(port_str)
                assert port > 45000, f"Port {port} is not above 45000"

    def test_web_server_respects_custom_port(self):
        """Test that web server uses custom port when specified."""
        custom_port = 48888

        result = subprocess.run(
            ["python", "-m", "audiomason", "web", "--port", str(custom_port)],
            capture_output=True,
            text=True,
            timeout=3,
        )

        output = result.stdout + result.stderr

        # Verify custom port is used
        assert str(custom_port) in output or f":{custom_port}" in output

    @pytest.mark.skip(reason="Web server runs in foreground - waiting for background mode")
    def test_web_server_actually_listens(self):
        """Test that web server actually opens a socket (requires background mode)."""
        # This test would verify the server actually binds to the port
        # Requires web server to run in background with proper daemonization
        pass
