"""Checkpoint system for resume support.

Allows saving and restoring processing state so work can be resumed
after interruption (Ctrl+C, crash, reboot).
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

from audiomason.core.context import ProcessingContext
from audiomason.core.errors import FileError


class CheckpointManager:
    """Manage checkpoints for resume support."""

    def __init__(self, checkpoint_dir: Path | None = None) -> None:
        """Initialize checkpoint manager.

        Args:
            checkpoint_dir: Directory for checkpoint files
        """
        self.checkpoint_dir = checkpoint_dir or Path.home() / ".audiomason" / "checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(self, context: ProcessingContext) -> Path:
        """Save context to checkpoint file.

        Args:
            context: Processing context to save

        Returns:
            Path to checkpoint file

        Raises:
            FileError: If save fails
        """
        checkpoint_file = self.checkpoint_dir / f"{context.id}.json"

        try:
            # Convert context to dict
            data = {
                "id": context.id,
                "source": str(context.source),
                "state": context.state.value,
                "current_step": context.current_step,
                "progress": context.progress,
                "completed_steps": context.completed_steps,
                # Metadata
                "author": context.author,
                "title": context.title,
                "year": context.year,
                "narrator": context.narrator,
                "series": context.series,
                "series_number": context.series_number,
                "genre": context.genre,
                "language": context.language,
                "isbn": context.isbn,
                # Cover
                "cover_choice": context.cover_choice.value if context.cover_choice else None,
                "cover_url": context.cover_url,
                # Processing options
                "split_chapters": context.split_chapters,
                "loudnorm": context.loudnorm,
                "target_bitrate": context.target_bitrate,
                # Paths
                "stage_dir": str(context.stage_dir) if context.stage_dir else None,
                "output_path": str(context.output_path) if context.output_path else None,
                # Files
                "converted_files": [str(f) for f in context.converted_files],
                "cover_path": str(context.cover_path) if context.cover_path else None,
                # Timing
                "timings": context.timings,
                "start_time": context.start_time,
                "end_time": context.end_time,
                # Errors
                "warnings": context.warnings,
            }

            # Write JSON
            with open(checkpoint_file, "w") as f:
                json.dump(data, f, indent=2)

            context.checkpoint_path = checkpoint_file
            return checkpoint_file

        except Exception as e:
            raise FileError(f"Failed to save checkpoint: {e}") from e

    def load_checkpoint(self, context_id: str) -> ProcessingContext:
        """Load context from checkpoint file.

        Args:
            context_id: Context ID to load

        Returns:
            Restored ProcessingContext

        Raises:
            FileError: If load fails
        """
        checkpoint_file = self.checkpoint_dir / f"{context_id}.json"

        if not checkpoint_file.exists():
            raise FileError(f"Checkpoint not found: {context_id}")

        try:
            with open(checkpoint_file) as f:
                data = json.load(f)

            # Reconstruct context
            from audiomason.core.context import CoverChoice, State

            context = ProcessingContext(
                id=data["id"],
                source=Path(data["source"]),
            )

            # Restore state
            context.state = State(data["state"])
            context.current_step = data.get("current_step")
            context.progress = data.get("progress", 0.0)
            context.completed_steps = data.get("completed_steps", [])

            # Restore metadata
            context.author = data.get("author")
            context.title = data.get("title")
            context.year = data.get("year")
            context.narrator = data.get("narrator")
            context.series = data.get("series")
            context.series_number = data.get("series_number")
            context.genre = data.get("genre")
            context.language = data.get("language")
            context.isbn = data.get("isbn")

            # Restore cover
            if data.get("cover_choice"):
                context.cover_choice = CoverChoice(data["cover_choice"])
            context.cover_url = data.get("cover_url")

            # Restore options
            context.split_chapters = data.get("split_chapters", False)
            context.loudnorm = data.get("loudnorm", False)
            context.target_bitrate = data.get("target_bitrate", "128k")

            # Restore paths
            if data.get("stage_dir"):
                context.stage_dir = Path(data["stage_dir"])
            if data.get("output_path"):
                context.output_path = Path(data["output_path"])

            # Restore files
            context.converted_files = [Path(f) for f in data.get("converted_files", [])]
            if data.get("cover_path"):
                context.cover_path = Path(data["cover_path"])

            # Restore timing
            context.timings = data.get("timings", {})
            context.start_time = data.get("start_time")
            context.end_time = data.get("end_time")

            # Restore warnings
            context.warnings = data.get("warnings", [])

            context.checkpoint_path = checkpoint_file

            return context

        except Exception as e:
            raise FileError(f"Failed to load checkpoint: {e}") from e

    def list_checkpoints(self) -> list[dict[str, Any]]:
        """List all available checkpoints.

        Returns:
            List of checkpoint info dicts
        """
        checkpoints = []

        for checkpoint_file in self.checkpoint_dir.glob("*.json"):
            try:
                with open(checkpoint_file) as f:
                    data = json.load(f)

                checkpoints.append(
                    {
                        "id": data["id"],
                        "title": data.get("title", "Unknown"),
                        "author": data.get("author", "Unknown"),
                        "state": data.get("state", "unknown"),
                        "progress": data.get("progress", 0.0),
                        "file": checkpoint_file,
                    }
                )
            except Exception:
                continue

        return checkpoints

    def delete_checkpoint(self, context_id: str) -> None:
        """Delete checkpoint file.

        Args:
            context_id: Context ID to delete
        """
        checkpoint_file = self.checkpoint_dir / f"{context_id}.json"
        if checkpoint_file.exists():
            checkpoint_file.unlink()

    def cleanup_old_checkpoints(self, days: int = 7) -> int:
        """Delete checkpoints older than N days.

        Args:
            days: Age threshold in days

        Returns:
            Number of deleted checkpoints
        """
        import time

        threshold = time.time() - (days * 24 * 60 * 60)
        deleted = 0

        for checkpoint_file in self.checkpoint_dir.glob("*.json"):
            if checkpoint_file.stat().st_mtime < threshold:
                checkpoint_file.unlink()
                deleted += 1

        return deleted
