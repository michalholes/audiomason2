"""Daemon plugin - watch folders and auto-process."""

from __future__ import annotations

import asyncio
import signal
import time
import uuid
from pathlib import Path
from typing import Any

from audiomason.core import (
    JobState,
    PluginLoader,
    ProcessingContext,
    State,
)
from audiomason.core.config_service import ConfigService
from audiomason.core.logging import get_logger
from audiomason.core.orchestration import Orchestrator
from audiomason.core.orchestration_models import ProcessRequest
from audiomason.core.plugin_registry import PluginRegistry

logger = get_logger(__name__)


class DaemonPlugin:
    """Daemon mode - watch folders and auto-process new files."""

    def __init__(self, config: dict | None = None) -> None:
        """Initialize daemon plugin.

        Args:
            config: Plugin configuration
        """
        self.config = config or {}
        self.watch_folders = self.config.get("watch_folders", [])
        self.interval = self.config.get("interval", 30)
        self.on_success = self.config.get("on_success", "move_to_output")
        self.on_error = self.config.get("on_error", "move_to_error")

        self.running = False
        self.processed_files: set[Path] = set()

    async def run(self) -> None:
        """Run daemon - main entry point."""
        logger.info("AudioMason Daemon Mode")
        logger.info(f"Watch folders: {len(self.watch_folders)}")
        for folder in self.watch_folders:
            logger.info(f"  * {folder}")
        logger.info(f"Check interval: {self.interval}s")
        logger.info("Press Ctrl+C to stop")

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self.running = True

        # Load plugins and pipeline
        plugins_dir = Path(__file__).parent.parent
        loader = PluginLoader(
            builtin_plugins_dir=plugins_dir, registry=PluginRegistry(ConfigService())
        )

        # Load required plugins
        for plugin_name in ["audio_processor", "file_io"]:
            plugin_dir = plugins_dir / plugin_name
            if plugin_dir.exists():
                loader.load_plugin(plugin_dir, validate=False)

        pipeline_path = plugins_dir.parent / "pipelines" / "minimal.yaml"
        orch = Orchestrator()

        # Main watch loop
        while self.running:
            try:
                await self._check_folders(orch, loader, pipeline_path)
                await asyncio.sleep(self.interval)
            except Exception as e:
                logger.error(f"Error in daemon loop: {e}")
                await asyncio.sleep(self.interval)

    async def _check_folders(
        self, orch: Orchestrator, loader: PluginLoader, pipeline_path: Path
    ) -> None:
        """Check watch folders for new files.

        Args:
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

                logger.info(f"Found new file: {file_path.name}")

                try:
                    await self._process_file(file_path, orch, loader, pipeline_path)
                    self.processed_files.add(file_path)
                except Exception as e:
                    logger.error(f"Error processing {file_path.name}: {e}")

            # Also check for Opus files
            for file_path in folder_path.glob("*.opus"):
                if file_path in self.processed_files:
                    continue

                if not self._is_file_stable(file_path):
                    continue

                logger.info(f"Found new file: {file_path.name}")

                try:
                    await self._process_file(file_path, orch, loader, pipeline_path)
                    self.processed_files.add(file_path)
                except Exception as e:
                    logger.error(f"Error processing {file_path.name}: {e}")

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
        self, file_path: Path, orch: Orchestrator, loader: PluginLoader, pipeline_path: Path
    ) -> None:
        """Process single file.

        Args:
            file_path: File to process
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

        logger.info("Processing...")

        # Process via core orchestration (jobs)
        job_id = orch.start_process(
            ProcessRequest(
                contexts=[context],
                pipeline_path=pipeline_path,
                plugin_loader=loader,
            )
        )

        offset = 0
        while True:
            job = orch.get_job(job_id)
            chunk, offset = orch.read_log(job_id, offset=offset)
            if chunk:
                for line in chunk.splitlines():
                    logger.verbose(line)

            if job.state in (JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED):
                break

            await asyncio.sleep(0.2)

        if job.state != JobState.SUCCEEDED:
            logger.error("Failed")

            if job.error:
                logger.error(f"Job error: {job.error}")

            if self.on_error == "move_to_error":
                error_dir = file_path.parent / "error"
                error_dir.mkdir(exist_ok=True)
                file_path.rename(error_dir / file_path.name)
                logger.info(f"Moved to: {error_dir}")
            elif self.on_error == "delete":
                file_path.unlink()
                logger.info("Deleted source file")
        else:
            logger.info("Success")

            if self.on_success == "move_to_output":
                # Already moved by pipeline
                pass
            elif self.on_success == "delete" and file_path.exists():
                file_path.unlink()
                logger.info("Deleted source file")

    def _handle_signal(self, signum: int, frame: Any) -> None:
        """Handle shutdown signal.

        Args:
            signum: Signal number
            frame: Stack frame
        """
        logger.info("Shutting down daemon...")
        self.running = False
