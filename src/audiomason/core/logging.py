"""Centralized logging system for AudioMason.

Provides unified logging across all plugins with 4 verbosity levels:
- QUIET (0): Warnings + errors
- NORMAL (1): Info + warnings + errors
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

import sys
from collections.abc import Callable
from enum import IntEnum
from pathlib import Path

from audiomason.core.config import LoggingPolicy
from audiomason.core.log_bus import LogRecord, get_log_bus


class VerbosityLevel(IntEnum):
    """Verbosity levels for AudioMason."""

    QUIET = 0  # Warnings + errors
    NORMAL = 1  # Info + warnings + errors
    VERBOSE = 2  # Detailed info
    DEBUG = 3  # Everything


# Global verbosity level
_VERBOSITY: VerbosityLevel = VerbosityLevel.NORMAL

# Deprecated log file path (kept for compatibility; core does not write files)
_DEPRECATED_LOG_FILE: Path | None = None

# Color support
_USE_COLORS: bool = True

# Backward compatible log sink
_LOG_SINK: Callable[[str], None] | None = None
_LEGACY_SINK_ADAPTER: Callable[[LogRecord], None] | None = None


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


def apply_logging_policy(policy: LoggingPolicy) -> None:
    """Apply a resolved LoggingPolicy to core logging.

    This bridges resolver output to the core logger's global verbosity state.
    """
    # Respect resolver policy deterministically.
    if policy.emit_debug:
        set_verbosity(VerbosityLevel.DEBUG)
    elif policy.emit_info or policy.emit_progress:
        set_verbosity(VerbosityLevel.NORMAL)
    else:
        # quiet (errors + warnings) in current core logging model
        set_verbosity(VerbosityLevel.QUIET)


def set_log_file(path: Path | str | None) -> None:
    """Deprecated: Core no longer writes a file-backed system log.

    This function is kept for compatibility with existing callers. It stores
    the last provided path but does not create directories or write to files.

    Args:
        path: Path to log file or None.
    """
    global _DEPRECATED_LOG_FILE
    _DEPRECATED_LOG_FILE = None if path is None else Path(path)


def set_colors(enabled: bool) -> None:
    """Enable or disable colored output.

    Args:
        enabled: Whether to use colors
    """
    global _USE_COLORS
    _USE_COLORS = enabled


def set_log_sink(sink: Callable[[str], None] | None) -> None:
    """Set a global log sink callback.

    Backward compatible adapter over LogBus.

    Args:
        sink: Callback receiving a single log line, or None to disable.
    """
    global _LOG_SINK
    global _LEGACY_SINK_ADAPTER

    if _LEGACY_SINK_ADAPTER is not None:
        get_log_bus().unsubscribe_all(_LEGACY_SINK_ADAPTER)
        _LEGACY_SINK_ADAPTER = None

    _LOG_SINK = sink

    if sink is None:
        return

    def _adapter(rec: LogRecord) -> None:
        try:
            sink(rec.plain)
        except Exception:
            return

    _LEGACY_SINK_ADAPTER = _adapter
    get_log_bus().subscribe_all(_adapter)


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
        get_log_bus().publish(LogRecord(level_name=level_name, plain=plain, logger_name=self.name))

        # Console output
        print(formatted, file=sys.stderr if level_name == "ERROR" else sys.stdout)

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
        """Log warning message (verbosity >= QUIET).

        Args:
            message: Message to log
        """
        self._log(VerbosityLevel.QUIET, "WARNING", message)

    def error(self, message: str) -> None:
        """Log error message (always shown).

        Args:
            message: Message to log
        """
        formatted = self._format_message("ERROR", message)

        plain = f"[error] {message}"
        get_log_bus().publish(LogRecord(level_name="ERROR", plain=plain, logger_name=self.name))

        print(formatted, file=sys.stderr)


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
