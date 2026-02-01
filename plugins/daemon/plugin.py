"""Daemon plugin - watch folders and auto-process."""

from __future__ import annotations

import asyncio
import signal
import time
import uuid
from pathlib import Path

from audiomason.core import (
    PipelineExecutor,
    PluginLoader,
    ProcessingContext,
    State,
)


class VerbosityLevel:
    """Verbosity levels."""

    QUIET = 0  # Errors only
    NORMAL = 1  # Progress + warnings
    VERBOSE = 2  # Detailed info
    DEBUG = 3  # Everything


class DaemonPlugin:
    """Daemon mode - watch folders and auto-process new files."""

    def __init__(self, config: dict | None = None) -> None:
        """Initialize daemon plugin.

        Args:
            config: Plugin configuration
        """
        self.config = config or {}
        self.verbosity = VerbosityLevel.NORMAL
        self.watch_folders = self.config.get("watch_folders", [])
        self.interval = self.config.get("interval", 30)
        self.on_success = self.config.get("on_success", "move_to_output")
        self.on_error = self.config.get("on_error", "move_to_error")

        self.running = False
        self.processed_files: set[Path] = set()

    async def run(self) -> None:
        """Run daemon - main entry point."""
        if self.verbosity >= VerbosityLevel.NORMAL:
            print("🔄 AudioMason Daemon Mode")
            print()
            print(f"Watch folders: {len(self.watch_folders)}")
            for folder in self.watch_folders:
                print(f"  • {folder}")
            print(f"Check interval: {self.interval}s")
            print()
            print("Press Ctrl+C to stop")
            print()

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self.running = True

        # Load plugins and pipeline
        plugins_dir = Path(__file__).parent.parent
        loader = PluginLoader(builtin_plugins_dir=plugins_dir)

        # Load required plugins
        for plugin_name in ["audio_processor", "file_io"]:
            plugin_dir = plugins_dir / plugin_name
            if plugin_dir.exists():
                loader.load_plugin(plugin_dir, validate=False)

        pipeline_path = plugins_dir.parent / "pipelines" / "minimal.yaml"
        executor = PipelineExecutor(loader)

        # Main watch loop
        while self.running:
            try:
                await self._check_folders(executor, pipeline_path)
                await asyncio.sleep(self.interval)
            except Exception as e:
                if self.verbosity >= VerbosityLevel.NORMAL:
                    print(f"Error in daemon loop: {e}")
                await asyncio.sleep(self.interval)

    async def _check_folders(self, executor: PipelineExecutor, pipeline_path: Path) -> None:
        """Check watch folders for new files.

        Args:
            executor: Pipeline executor
            pipeline_path: Pipeline YAML path
        """
        for folder in self.watch_folders:
            folder_path = Path(folder).expanduser()

            if not folder_path.exists():
                continue

            # Find new audio files
            for file_path in folder_path.glob("*.m4a"):
                if file_path in self.processed_files:
                    continue

                # Check if file is stable (not being written)
                if not self._is_file_stable(file_path):
                    continue

                if self.verbosity >= VerbosityLevel.NORMAL:
                    print(f"📁 Found new file: {file_path.name}")

                try:
                    await self._process_file(file_path, executor, pipeline_path)
                    self.processed_files.add(file_path)
                except Exception as e:
                    print(f"   ❌ Error: {e}")

            # Also check for Opus files
            for file_path in folder_path.glob("*.opus"):
                if file_path in self.processed_files:
                    continue

                if not self._is_file_stable(file_path):
                    continue

                if self.verbosity >= VerbosityLevel.NORMAL:
                    print(f"📁 Found new file: {file_path.name}")

                try:
                    await self._process_file(file_path, executor, pipeline_path)
                    self.processed_files.add(file_path)
                except Exception as e:
                    print(f"   ❌ Error: {e}")

    def _is_file_stable(self, file_path: Path, threshold: float = 5.0) -> bool:
        """Check if file is stable (not being written).

        Args:
            file_path: File to check
            threshold: Seconds file must be unchanged

        Returns:
            True if file is stable
        """
        try:
            mtime = file_path.stat().st_mtime
            age = time.time() - mtime
            return age > threshold
        except Exception:
            return False

    async def _process_file(
        self, file_path: Path, executor: PipelineExecutor, pipeline_path: Path
    ) -> None:
        """Process single file.

        Args:
            file_path: File to process
            executor: Pipeline executor
            pipeline_path: Pipeline YAML path
        """
        # Create context with defaults
        context = ProcessingContext(
            id=str(uuid.uuid4()),
            source=file_path,
            author="Unknown",  # Daemon uses defaults
            title=file_path.stem,
            state=State.PROCESSING,
        )

        if self.verbosity >= VerbosityLevel.NORMAL:
            print("   ⚡ Processing...")

        # Process
        result = await executor.execute_from_yaml(pipeline_path, context)

        if result.has_errors:
            print("   ❌ Failed with errors")

            if self.on_error == "move_to_error":
                error_dir = file_path.parent / "error"
                error_dir.mkdir(exist_ok=True)
                file_path.rename(error_dir / file_path.name)
                if self.verbosity >= VerbosityLevel.NORMAL:
                    print(f"   📁 Moved to: {error_dir}")
            elif self.on_error == "delete":
                file_path.unlink()
                if self.verbosity >= VerbosityLevel.NORMAL:
                    print("   🗑️  Deleted source file")
        else:
            if self.verbosity >= VerbosityLevel.NORMAL:
                print("   ✅ Success!")

            if self.on_success == "move_to_output":
                # Already moved by pipeline
                pass
            elif self.on_success == "delete":
                if file_path.exists():
                    file_path.unlink()
                    if self.verbosity >= VerbosityLevel.NORMAL:
                        print("   🗑️  Deleted source file")

    def _handle_signal(self, signum: int, frame: Any) -> None:
        """Handle shutdown signal.

        Args:
            signum: Signal number
            frame: Stack frame
        """
        if self.verbosity >= VerbosityLevel.NORMAL:
            print()
            print("🛑 Shutting down daemon...")
        self.running = False
