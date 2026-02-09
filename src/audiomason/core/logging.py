"""Centralized logging system for AudioMason.

Provides unified logging across all plugins with 4 verbosity levels:
- QUIET (0): Errors only
- NORMAL (1): Progress + warnings + errors
- VERBOSE (2): Detailed info
- DEBUG (3): Everything including internal state

Usage:
    from audiomason.core.logging import get_logger, set_verbosity

    logger = get_logger(__name__)
    set_verbosity(2)  # VERBOSE

    logger.debug("Internal state")
    logger.verbose("Processing file X")
    logger.info("Started processing")
    logger.warning("Cover not found")
    logger.error("Failed to convert")
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Callable
from enum import IntEnum
from pathlib import Path


class VerbosityLevel(IntEnum):
    """Verbosity levels for AudioMason."""

    QUIET = 0  # Errors only
    NORMAL = 1  # Progress + warnings + errors
    VERBOSE = 2  # Detailed info
    DEBUG = 3  # Everything


# Global verbosity level
_VERBOSITY: VerbosityLevel = VerbosityLevel.NORMAL

# Log file path (optional)
_LOG_FILE: Path | None = None

# Color support
_USE_COLORS: bool = True

# Optional log sink for job-aware routing (Phase 1)
_LOG_SINK: Callable[[str], None] | None = None


def set_verbosity(level: int | VerbosityLevel) -> None:
    """Set global verbosity level.

    Args:
        level: Verbosity level (0-3 or VerbosityLevel enum)
    """
    global _VERBOSITY

    if isinstance(level, int):
        level = VerbosityLevel(level)

    _VERBOSITY = level


def get_verbosity() -> VerbosityLevel:
    """Get current verbosity level.

    Returns:
        Current verbosity level
    """
    return _VERBOSITY


def set_log_file(path: Path | str | None) -> None:
    """Set log file path.

    Args:
        path: Path to log file or None to disable file logging
    """
    global _LOG_FILE

    if path:
        _LOG_FILE = Path(path)
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    else:
        _LOG_FILE = None


def set_colors(enabled: bool) -> None:
    """Enable or disable colored output.

    Args:
        enabled: Whether to use colors
    """
    global _USE_COLORS
    _USE_COLORS = enabled


def set_log_sink(sink: Callable[[str], None] | None) -> None:
    """Set a global log sink callback.

    When set, every log line emitted via core logging is forwarded to the sink
    as plain text. When None, logging behaves as before.

    Args:
        sink: Callback receiving a single log line, or None to disable.
    """
    global _LOG_SINK
    _LOG_SINK = sink


def get_log_sink() -> Callable[[str], None] | None:
    """Get the current global log sink callback (if any)."""
    return _LOG_SINK


class AudioMasonLogger:
    """Logger for AudioMason with verbosity support."""

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "VERBOSE": "\033[34m",  # Blue
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "RESET": "\033[0m",
    }

    def __init__(self, name: str):
        """Initialize logger.

        Args:
            name: Logger name (usually module name)
        """
        self.name = name

    def _should_log(self, level: VerbosityLevel) -> bool:
        """Check if message should be logged.

        Args:
            level: Required verbosity level

        Returns:
            True if should log
        """
        return level <= _VERBOSITY

    def _format_message(self, level: str, message: str) -> str:
        """Format log message.

        Args:
            level: Log level name
            message: Message text

        Returns:
            Formatted message
        """
        # Add color if enabled
        if _USE_COLORS and sys.stdout.isatty():
            color = self.COLORS.get(level, "")
            reset = self.COLORS["RESET"]
            return f"{color}[{level.lower()}]{reset} {message}"
        else:
            return f"[{level.lower()}] {message}"

    def _log(self, level: VerbosityLevel, level_name: str, message: str) -> None:
        """Internal logging method.

        Args:
            level: Required verbosity level
            level_name: Level name for display
            message: Message to log
        """
        if not self._should_log(level):
            return

        formatted = self._format_message(level_name, message)

        plain = f"[{level_name.lower()}] {message}"
        if _LOG_SINK is not None:
            with contextlib.suppress(Exception):
                _LOG_SINK(plain)

        # Console output
        print(formatted, file=sys.stderr if level_name == "ERROR" else sys.stdout)

        # File output (if configured)
        if _LOG_FILE:
            try:
                with open(_LOG_FILE, "a") as f:
                    # Remove colors for file
                    plain = f"[{level_name.lower()}] {message}\n"
                    f.write(plain)
            except Exception:
                pass  # Don't crash if logging fails

    def debug(self, message: str) -> None:
        """Log debug message (verbosity >= DEBUG).

        Args:
            message: Message to log
        """
        self._log(VerbosityLevel.DEBUG, "DEBUG", message)

    def verbose(self, message: str) -> None:
        """Log verbose message (verbosity >= VERBOSE).

        Args:
            message: Message to log
        """
        self._log(VerbosityLevel.VERBOSE, "VERBOSE", message)

    def info(self, message: str) -> None:
        """Log info message (verbosity >= NORMAL).

        Args:
            message: Message to log
        """
        self._log(VerbosityLevel.NORMAL, "INFO", message)

    def warning(self, message: str) -> None:
        """Log warning message (always shown except QUIET).

        Args:
            message: Message to log
        """
        self._log(VerbosityLevel.NORMAL, "WARNING", message)

    def error(self, message: str) -> None:
        """Log error message (always shown).

        Args:
            message: Message to log
        """
        # Errors are shown even in QUIET mode
        formatted = self._format_message("ERROR", message)

        plain = f"[error] {message}"
        if _LOG_SINK is not None:
            with contextlib.suppress(Exception):
                _LOG_SINK(plain)

        print(formatted, file=sys.stderr)

        # File output
        if _LOG_FILE:
            try:
                with open(_LOG_FILE, "a") as f:
                    f.write(f"[error] {message}\n")
            except Exception:
                pass


# Logger registry
_LOGGERS: dict[str, AudioMasonLogger] = {}


def get_logger(name: str = __name__) -> AudioMasonLogger:
    """Get logger instance for module.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Logger instance
    """
    if name not in _LOGGERS:
        _LOGGERS[name] = AudioMasonLogger(name)

    return _LOGGERS[name]


# Convenience functions for quick logging
def debug(message: str) -> None:
    """Log debug message."""
    get_logger("audiomason").debug(message)


def verbose(message: str) -> None:
    """Log verbose message."""
    get_logger("audiomason").verbose(message)


def info(message: str) -> None:
    """Log info message."""
    get_logger("audiomason").info(message)


def warning(message: str) -> None:
    """Log warning message."""
    get_logger("audiomason").warning(message)


def error(message: str) -> None:
    """Log error message."""
    get_logger("audiomason").error(message)
