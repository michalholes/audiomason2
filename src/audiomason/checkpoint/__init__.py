"""Checkpoint system for resume support.

Allows saving and restoring processing state so work can be resumed
after interruption (Ctrl+C, crash, reboot).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypeGuard, cast

from audiomason.core.context import ProcessingContext
from audiomason.core.errors import FileError
from audiomason.core.serde import json_loads_object


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _read_json_dict(path: Path) -> dict[str, object]:
    loaded = json_loads_object(path.read_text(encoding="utf-8"))
    if not _is_str_object_dict(loaded):
        raise FileError(f"Invalid checkpoint format: {path}")
    return loaded


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _as_bool(value: object, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return default


def _as_float(value: object, *, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items = cast(list[object], value)
    return [str(item) for item in items]


def _as_timings(value: object) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    source = cast(dict[object, object], value)
    out: dict[str, float] = {}
    for key, item in source.items():
        if isinstance(item, int | float):
            out[str(key)] = float(item)
    return out


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
                json.dump(data, f, indent=2, ensure_ascii=True)

            context.checkpoint_path = checkpoint_file
            return checkpoint_file

        except Exception as e:
            raise FileError(f"Failed to save checkpoint: {e}") from e

    def save_job_failure_checkpoint(
        self, job_id: str, *, kind: str, error: str, meta: dict[str, object]
    ) -> Path:
        """Save a minimal failure checkpoint for a job.

        This is used for phase-contract failures where a ProcessingContext may not be available
        (e.g. wizard jobs).

        The file content is intentionally minimal and deterministic (no timestamps).

        Args:
            job_id: Job identifier.
            kind: Job kind (e.g. "process", "wizard").
            error: Error string.
            meta: Job meta mapping.

        Returns:
            Path to the checkpoint file.
        """
        checkpoint_file = self.checkpoint_dir / f"job_{job_id}.json"
        data = {"job_id": job_id, "kind": kind, "error": error, "meta": meta}
        try:
            with open(checkpoint_file, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=True)
            return checkpoint_file
        except Exception as e:
            raise FileError(f"Failed to save job checkpoint: {e}") from e

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
            data = _read_json_dict(checkpoint_file)

            # Reconstruct context
            from audiomason.core.context import CoverChoice, State

            source = _as_str(data.get("source"))
            state_raw = _as_str(data.get("state"))
            if source is None or state_raw is None:
                raise FileError(f"Invalid checkpoint payload: {checkpoint_file}")

            context = ProcessingContext(
                id=str(data.get("id", context_id)),
                source=Path(source),
            )

            # Restore state
            context.state = State(state_raw)
            context.current_step = _as_str(data.get("current_step"))
            context.progress = _as_float(data.get("progress", 0.0), default=0.0)
            context.completed_steps = _as_str_list(data.get("completed_steps", []))

            # Restore metadata
            context.author = _as_str(data.get("author"))
            context.title = _as_str(data.get("title"))
            context.year = _as_int(data.get("year"))
            context.narrator = _as_str(data.get("narrator"))
            context.series = _as_str(data.get("series"))
            context.series_number = _as_int(data.get("series_number"))
            context.genre = _as_str(data.get("genre"))
            context.language = _as_str(data.get("language"))
            context.isbn = _as_str(data.get("isbn"))

            # Restore cover
            cover_choice_raw = _as_str(data.get("cover_choice"))
            if cover_choice_raw:
                context.cover_choice = CoverChoice(cover_choice_raw)
            context.cover_url = _as_str(data.get("cover_url"))

            # Restore options
            context.split_chapters = _as_bool(data.get("split_chapters"), default=False)
            context.loudnorm = _as_bool(data.get("loudnorm"), default=False)
            context.target_bitrate = _as_str(data.get("target_bitrate")) or "128k"

            # Restore paths
            stage_dir_raw = _as_str(data.get("stage_dir"))
            if stage_dir_raw:
                context.stage_dir = Path(stage_dir_raw)
            output_path_raw = _as_str(data.get("output_path"))
            if output_path_raw:
                context.output_path = Path(output_path_raw)

            # Restore files
            context.converted_files = [
                Path(item) for item in _as_str_list(data.get("converted_files", []))
            ]
            cover_path_raw = _as_str(data.get("cover_path"))
            if cover_path_raw:
                context.cover_path = Path(cover_path_raw)

            # Restore timing
            context.timings = _as_timings(data.get("timings", {}))
            start_time_raw = data.get("start_time")
            end_time_raw = data.get("end_time")
            context.start_time = _as_float(start_time_raw) if start_time_raw is not None else None
            context.end_time = _as_float(end_time_raw) if end_time_raw is not None else None

            # Restore warnings
            context.warnings = _as_str_list(data.get("warnings", []))

            context.checkpoint_path = checkpoint_file

            return context

        except Exception as e:
            raise FileError(f"Failed to load checkpoint: {e}") from e

    def list_checkpoints(self) -> list[dict[str, object]]:
        """List all available checkpoints.

        Returns:
            List of checkpoint info dicts
        """
        checkpoints: list[dict[str, object]] = []

        for checkpoint_file in self.checkpoint_dir.glob("*.json"):
            try:
                data = _read_json_dict(checkpoint_file)
                checkpoint_id = _as_str(data.get("id")) or ""

                checkpoints.append(
                    {
                        "id": checkpoint_id,
                        "title": _as_str(data.get("title")) or "Unknown",
                        "author": _as_str(data.get("author")) or "Unknown",
                        "state": _as_str(data.get("state")) or "unknown",
                        "progress": _as_float(data.get("progress", 0.0), default=0.0),
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
