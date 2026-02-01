"""Tests for centralized logging system."""

import tempfile
from pathlib import Path

from audiomason.core.logging import (
    VerbosityLevel,
    get_logger,
    get_verbosity,
    set_colors,
    set_log_file,
    set_verbosity,
)


class TestVerbosityLevel:
    """Test VerbosityLevel enum."""

    def test_verbosity_values(self):
        """Test verbosity level values."""
        assert VerbosityLevel.QUIET == 0
        assert VerbosityLevel.NORMAL == 1
        assert VerbosityLevel.VERBOSE == 2
        assert VerbosityLevel.DEBUG == 3

    def test_verbosity_ordering(self):
        """Test verbosity level ordering."""
        assert VerbosityLevel.QUIET < VerbosityLevel.NORMAL
        assert VerbosityLevel.NORMAL < VerbosityLevel.VERBOSE
        assert VerbosityLevel.VERBOSE < VerbosityLevel.DEBUG


class TestLoggingSetup:
    """Test logging setup functions."""

    def test_set_get_verbosity(self):
        """Test setting and getting verbosity."""
        # Test with int
        set_verbosity(2)
        assert get_verbosity() == VerbosityLevel.VERBOSE

        # Test with enum
        set_verbosity(VerbosityLevel.DEBUG)
        assert get_verbosity() == VerbosityLevel.DEBUG

        # Reset
        set_verbosity(VerbosityLevel.NORMAL)

    def test_set_log_file(self):
        """Test setting log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"

            set_log_file(log_path)

            # Log something
            logger = get_logger("test")
            set_verbosity(VerbosityLevel.NORMAL)
            logger.info("test message")

            # Check file was created and contains message
            assert log_path.exists()
            content = log_path.read_text()
            assert "test message" in content

            # Clean up
            set_log_file(None)

    def test_set_colors(self):
        """Test setting colors."""
        set_colors(False)
        # No easy way to test output, just verify it doesn't crash
        logger = get_logger("test")
        logger.info("test")

        set_colors(True)


class TestLogger:
    """Test AudioMasonLogger class."""

    def setup_method(self):
        """Set up test."""
        set_verbosity(VerbosityLevel.NORMAL)
        set_log_file(None)
        self.logger = get_logger("test")

    def test_logger_creation(self):
        """Test logger creation."""
        logger1 = get_logger("test1")
        logger2 = get_logger("test2")
        logger3 = get_logger("test1")  # Should return same instance

        assert logger1 is not logger2
        assert logger1 is logger3

    def test_debug_level(self):
        """Test debug level logging."""
        # Debug should not show at NORMAL
        set_verbosity(VerbosityLevel.NORMAL)
        self.logger.debug("debug message")  # Should not crash

        # Debug should show at DEBUG
        set_verbosity(VerbosityLevel.DEBUG)
        self.logger.debug("debug message")  # Should not crash

    def test_verbose_level(self):
        """Test verbose level logging."""
        # Verbose should not show at NORMAL
        set_verbosity(VerbosityLevel.NORMAL)
        self.logger.verbose("verbose message")  # Should not crash

        # Verbose should show at VERBOSE
        set_verbosity(VerbosityLevel.VERBOSE)
        self.logger.verbose("verbose message")  # Should not crash

        # Verbose should show at DEBUG
        set_verbosity(VerbosityLevel.DEBUG)
        self.logger.verbose("verbose message")  # Should not crash

    def test_info_level(self):
        """Test info level logging."""
        # Info should show at NORMAL
        set_verbosity(VerbosityLevel.NORMAL)
        self.logger.info("info message")  # Should not crash

        # Info should not show at QUIET
        set_verbosity(VerbosityLevel.QUIET)
        self.logger.info("info message")  # Should not crash

    def test_warning_level(self):
        """Test warning level logging."""
        set_verbosity(VerbosityLevel.NORMAL)
        self.logger.warning("warning message")  # Should not crash

    def test_error_level(self):
        """Test error level logging."""
        # Errors always show
        set_verbosity(VerbosityLevel.QUIET)
        self.logger.error("error message")  # Should not crash

        set_verbosity(VerbosityLevel.NORMAL)
        self.logger.error("error message")  # Should not crash


class TestLogFile:
    """Test log file functionality."""

    def test_log_to_file(self):
        """Test logging to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "logs" / "test.log"

            set_log_file(log_path)
            set_verbosity(VerbosityLevel.VERBOSE)

            logger = get_logger("test")
            logger.debug("debug")
            logger.verbose("verbose")
            logger.info("info")
            logger.warning("warning")
            logger.error("error")

            # Check all messages were written
            content = log_path.read_text()
            assert "debug" not in content  # DEBUG not at VERBOSE
            assert "verbose" in content
            assert "info" in content
            assert "warning" in content
            assert "error" in content

            # Clean up
            set_log_file(None)

    def test_log_file_creation(self):
        """Test log file directory creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "nested" / "dir" / "test.log"

            # Directory should be created automatically
            set_log_file(log_path)

            logger = get_logger("test")
            set_verbosity(VerbosityLevel.NORMAL)
            logger.info("test")

            assert log_path.parent.exists()
            assert log_path.exists()

            # Clean up
            set_log_file(None)


class TestVerbosityFiltering:
    """Test verbosity level filtering."""

    def test_quiet_shows_only_errors(self):
        """Test QUIET shows only errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"
            set_log_file(log_path)
            set_verbosity(VerbosityLevel.QUIET)

            logger = get_logger("test")
            logger.debug("debug")
            logger.verbose("verbose")
            logger.info("info")
            logger.warning("warning")
            logger.error("error")

            content = log_path.read_text()
            assert "debug" not in content
            assert "verbose" not in content
            assert "info" not in content
            assert "warning" not in content
            assert "error" in content

            set_log_file(None)

    def test_normal_shows_info_and_above(self):
        """Test NORMAL shows info, warnings, and errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"
            set_log_file(log_path)
            set_verbosity(VerbosityLevel.NORMAL)

            logger = get_logger("test")
            logger.debug("debug")
            logger.verbose("verbose")
            logger.info("info")
            logger.warning("warning")
            logger.error("error")

            content = log_path.read_text()
            assert "debug" not in content
            assert "verbose" not in content
            assert "info" in content
            assert "warning" in content
            assert "error" in content

            set_log_file(None)

    def test_verbose_shows_verbose_and_above(self):
        """Test VERBOSE shows verbose, info, warnings, and errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"
            set_log_file(log_path)
            set_verbosity(VerbosityLevel.VERBOSE)

            logger = get_logger("test")
            logger.debug("debug")
            logger.verbose("verbose")
            logger.info("info")
            logger.warning("warning")
            logger.error("error")

            content = log_path.read_text()
            assert "debug" not in content
            assert "verbose" in content
            assert "info" in content
            assert "warning" in content
            assert "error" in content

            set_log_file(None)

    def test_debug_shows_everything(self):
        """Test DEBUG shows everything."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "test.log"
            set_log_file(log_path)
            set_verbosity(VerbosityLevel.DEBUG)

            logger = get_logger("test")
            logger.debug("debug")
            logger.verbose("verbose")
            logger.info("info")
            logger.warning("warning")
            logger.error("error")

            content = log_path.read_text()
            assert "debug" in content
            assert "verbose" in content
            assert "info" in content
            assert "warning" in content
            assert "error" in content

            set_log_file(None)
