"""Error handling with friendly messages."""

from __future__ import annotations


class AudioMasonError(Exception):
    """Base exception for all AudioMason errors."""

    def __init__(self, message: str, suggestion: str | None = None) -> None:
        self.message = message
        self.suggestion = suggestion
        super().__init__(message)

    def __str__(self) -> str:
        if self.suggestion:
            return f"{self.message}\nSuggestion: {self.suggestion}"
        return self.message


class PluginError(AudioMasonError):
    """Plugin-related error."""

    pass


class PluginNotFoundError(PluginError):
    """Plugin not found."""

    def __init__(self, plugin_name: str) -> None:
        super().__init__(
            f"Plugin '{plugin_name}' not found",
            f"Check available plugins with: audiomason plugins list",
        )


class PluginValidationError(PluginError):
    """Plugin failed validation."""

    pass


class ConfigError(AudioMasonError):
    """Configuration error."""

    pass


class PipelineError(AudioMasonError):
    """Pipeline execution error."""

    pass


class FileError(AudioMasonError):
    """File operation error."""

    pass


class CorruptedFileError(FileError):
    """File is corrupted."""

    def __init__(self, path: str) -> None:
        super().__init__(
            f"File '{path}' is corrupted or unreadable",
            "Try re-downloading or check file integrity",
        )


class DiskFullError(FileError):
    """Disk is full."""

    def __init__(self, path: str) -> None:
        super().__init__(
            f"Disk full: Cannot write to '{path}'",
            "Free up space and try again",
        )


class MetadataError(AudioMasonError):
    """Metadata-related error."""

    pass


class CoverError(AudioMasonError):
    """Cover-related error."""

    pass
