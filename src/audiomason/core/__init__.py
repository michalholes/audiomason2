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
from audiomason.core.interfaces import IUI, IEnricher, IProcessor, IProvider, IStorage
from audiomason.core.jobs import Job, JobService, JobState, JobStore, JobType
from audiomason.core.loader import PluginLoader, PluginManifest
from audiomason.core.logging import (
    VerbosityLevel,
    get_logger,
    get_verbosity,
    set_colors,
    set_log_file,
    set_verbosity,
)
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
    # Logging
    "VerbosityLevel",
    "get_logger",
    "set_verbosity",
    "get_verbosity",
    "set_log_file",
    "set_colors",
    # Jobs
    "Job",
    "JobType",
    "JobState",
    "JobStore",
    "JobService",
]


def main():
    """Main entry point for audiomason CLI."""
    import asyncio
    import importlib.util
    import sys
    from pathlib import Path

    def _run_cli(coro) -> None:
        """Run a coroutine in a dedicated event loop."""
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(coro)
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    # FIX BUG 6: Use proper method to find project root
    # Try multiple strategies to locate plugins directory

    # Strategy 1: Relative to installed package location
    core_location = Path(__file__).parent  # .../site-packages/audiomason/core
    package_root = core_location.parent  # .../site-packages/audiomason

    # Strategy 2: Development environment (git checkout)
    dev_plugins = package_root.parent.parent / "plugins"

    # Strategy 3: Installed package (look for plugins as sibling)
    installed_plugins = package_root.parent / "plugins"

    # Try to find plugins directory
    plugins_dir = None
    for candidate in [dev_plugins, installed_plugins]:
        if candidate.exists() and candidate.is_dir():
            plugins_dir = candidate
            break

    if plugins_dir is None:
        # Last resort: check environment variable
        import os

        env_plugins = os.getenv("AUDIOMASON_PLUGINS_DIR")
        if env_plugins:
            plugins_dir = Path(env_plugins)

    if plugins_dir is None or not plugins_dir.exists():
        print("Error: plugins directory not found")
        print("Tried:")
        print(f"  - {dev_plugins}")
        print(f"  - {installed_plugins}")
        print("Set AUDIOMASON_PLUGINS_DIR environment variable to specify location")
        sys.exit(1)

    # FIX BUG 1: Use importlib instead of manipulating sys.path with generic "plugin" name
    cli_plugin_file = plugins_dir / "cmd_interface" / "plugin.py"

    if not cli_plugin_file.exists():
        print(f"Error: CLI plugin not found at {cli_plugin_file}")
        sys.exit(1)

    try:
        # Load the CLI plugin module with a unique name
        spec = importlib.util.spec_from_file_location("audiomason_cli_plugin", cli_plugin_file)
        if spec is None or spec.loader is None:
            raise ImportError(f"Failed to load spec for {cli_plugin_file}")

        cli_module = importlib.util.module_from_spec(spec)
        sys.modules["audiomason_cli_plugin"] = cli_module
        spec.loader.exec_module(cli_module)

        # Get the CLIPlugin class
        cli_plugin_cls = cli_module.CLIPlugin

        cli = cli_plugin_cls()
        _run_cli(cli.run())

    except ImportError as e:
        print(f"Error: Failed to load CLI plugin: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(0)
