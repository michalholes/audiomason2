"""AudioMason v2 - Ultra-minimal core.

This is the microkernel of AudioMason v2.
Everything else is a plugin.
"""

__version__ = "2.0.0-alpha"

from audiomason.core.config import ConfigResolver
from audiomason.core.context import CoverChoice, PreflightResult, ProcessingContext, State
from audiomason.core.detection import (
    detect_chapters,
    detect_file_groups,
    detect_format,
    extract_existing_metadata,
    find_file_cover,
    guess_author_from_path,
    guess_title_from_path,
    guess_year_from_path,
    has_embedded_cover,
)
from audiomason.core.errors import (
    AudioMasonError,
    ConfigError,
    CorruptedFileError,
    CoverError,
    DiskFullError,
    FileError,
    MetadataError,
    PipelineError,
    PluginError,
    PluginNotFoundError,
    PluginValidationError,
)
from audiomason.core.events import EventBus, get_event_bus
from audiomason.core.interfaces import IEnricher, IProcessor, IProvider, IStorage, IUI
from audiomason.core.loader import PluginLoader, PluginManifest
from audiomason.core.pipeline import Pipeline, PipelineExecutor, PipelineStep

__all__ = [
    # Context
    "ProcessingContext",
    "PreflightResult",
    "State",
    "CoverChoice",
    # Interfaces
    "IProcessor",
    "IProvider",
    "IUI",
    "IStorage",
    "IEnricher",
    # Config
    "ConfigResolver",
    # Errors
    "AudioMasonError",
    "PluginError",
    "PluginNotFoundError",
    "PluginValidationError",
    "ConfigError",
    "PipelineError",
    "FileError",
    "CorruptedFileError",
    "DiskFullError",
    "MetadataError",
    "CoverError",
    # Events
    "EventBus",
    "get_event_bus",
    # Loader
    "PluginLoader",
    "PluginManifest",
    # Pipeline
    "PipelineExecutor",
    "Pipeline",
    "PipelineStep",
    # Detection
    "guess_author_from_path",
    "guess_title_from_path",
    "guess_year_from_path",
    "detect_file_groups",
    "extract_existing_metadata",
    "has_embedded_cover",
    "find_file_cover",
    "detect_chapters",
    "detect_format",
]


def main():
    """Main entry point for audiomason CLI."""
    import asyncio
    import sys
    from pathlib import Path
    
    # Find plugins directory
    project_root = Path(__file__).parent.parent.parent.parent
    plugins_dir = project_root / "plugins"
    
    if not plugins_dir.exists():
        print(f"Error: plugins directory not found at {plugins_dir}")
        sys.exit(1)
    
    # Add CLI plugin to path
    sys.path.insert(0, str(plugins_dir / "cli"))
    
    try:
        from plugin import CLIPlugin
        cli = CLIPlugin()
        asyncio.run(cli.run())
    except ImportError as e:
        print(f"Error: Failed to load CLI plugin: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(0)
