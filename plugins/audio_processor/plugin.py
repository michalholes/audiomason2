"""Audio processing plugin - converts M4A/Opus to MP3.

Based on AM1 audio.py functionality.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

from audiomason.core import ProcessingContext
from audiomason.core.errors import AudioMasonError


class FFmpegError(AudioMasonError):
    """FFmpeg operation failed."""

    pass


_SUPPORTED_FORMATS = {".m4a", ".m4b", ".opus", ".mp3"}
_CONVERTIBLE_FORMATS = {".m4a", ".m4b", ".opus"}
_CHAPTER_FORMATS = {".m4a", ".m4b"}


class AudioProcessorPlugin:
    """Audio processor plugin.

    Handles deterministic import conversion planning for Phase 2.
    """

    def __init__(self, config: dict | None = None) -> None:
        """Initialize plugin.

        Args:
            config: Plugin configuration
        """
        self.config = config or {}
        self.bitrate = self.config.get("bitrate", "128k")
        self.loudnorm = self.config.get("loudnorm", False)
        self.split_chapters = self.config.get("split_chapters", False)

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        """Process audio file.

        Args:
            context: Processing context

        Returns:
            Updated context with converted files
        """
        source = context.source
        stage_dir = context.stage_dir
        if not stage_dir:
            raise FFmpegError("Stage directory not set")

        fmt = self.source_format(source)
        if fmt not in _SUPPORTED_FORMATS:
            raise FFmpegError(f"Unsupported format: {fmt}")

        if fmt != ".mp3" and not self._check_ffmpeg():
            raise FFmpegError(
                "FFmpeg not found",
                "Install with: sudo apt-get install ffmpeg",
            )

        chapters: list[dict[str, Any]] = []
        if fmt in _CHAPTER_FORMATS:
            chapters = await self._detect_chapters(source)
            context.add_warning(f"M4A file: {len(chapters)} chapter(s) detected")
        elif fmt == ".mp3":
            context.add_warning("Source is already MP3, copying...")

        plan = self.plan_import_conversion(source, stage_dir, chapters=chapters)
        outputs = await self._execute_plan(plan)
        context.converted_files.extend(outputs)
        if plan and str(plan[0].get("operation")) == "split_chapter":
            context.add_warning(f"Split into {len(outputs)} files")
        return context

    def source_format(self, source: Path) -> str:
        """Return canonical lower-case source suffix."""
        return source.suffix.lower()

    def plan_import_conversion(
        self,
        source: Path,
        output_dir: Path,
        *,
        chapters: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Return deterministic conversion actions for import runtime."""
        fmt = self.source_format(source)
        if fmt not in _SUPPORTED_FORMATS:
            raise FFmpegError(f"Unsupported format: {fmt}")

        if fmt == ".mp3":
            return [
                {
                    "operation": "copy",
                    "order": 1,
                    "source": source,
                    "output": output_dir / source.name,
                    "source_format": fmt,
                    "target_format": ".mp3",
                }
            ]

        if fmt in _CHAPTER_FORMATS:
            split_plan = self._plan_split_actions(source, output_dir, chapters or [])
            if split_plan:
                return split_plan

        return [
            {
                "operation": "convert",
                "order": 1,
                "source": source,
                "output": output_dir / f"{source.stem}.mp3",
                "source_format": fmt,
                "target_format": ".mp3",
                "loudnorm": self.loudnorm,
            }
        ]

    def build_conversion_command(self, action: dict[str, Any]) -> list[str]:
        """Build deterministic FFmpeg command for a planned action."""
        operation = str(action.get("operation") or "")
        source = Path(action["source"])
        output = Path(action["output"])
        if operation not in {"convert", "split_chapter"}:
            raise FFmpegError(f"Unsupported conversion action: {operation}")

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
        ]
        if operation == "split_chapter":
            start = float(action["start_time"])
            end = float(action["end_time"])
            cmd.extend(["-ss", str(start), "-i", str(source), "-t", str(end - start), "-vn"])
        else:
            cmd.extend(["-i", str(source), "-vn"])
        if bool(action.get("loudnorm", False)):
            cmd.extend(["-af", "loudnorm=I=-16:LRA=11:TP=-1.5"])
        cmd.extend(
            [
                "-codec:a",
                "libmp3lame",
                "-q:a",
                "4",
                "-b:a",
                self.bitrate,
                str(output),
            ]
        )
        return cmd

    def _plan_split_actions(
        self,
        source: Path,
        output_dir: Path,
        chapters: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return deterministic chapter split actions when enabled."""
        if not self.split_chapters or len(chapters) < 2:
            return []

        plan: list[dict[str, Any]] = []
        for chapter_index, chapter in enumerate(chapters, 1):
            try:
                start = float(chapter["start_time"])
                end = float(chapter["end_time"])
            except Exception:
                return []
            if end <= start:
                return []
            plan.append(
                {
                    "operation": "split_chapter",
                    "order": chapter_index,
                    "chapter_index": chapter_index,
                    "source": source,
                    "output": output_dir / f"{chapter_index:02d}.mp3",
                    "source_format": self.source_format(source),
                    "target_format": ".mp3",
                    "start_time": start,
                    "end_time": end,
                    "loudnorm": self.loudnorm,
                }
            )
        return plan

    async def _execute_plan(self, plan: list[dict[str, Any]]) -> list[Path]:
        """Execute planned actions in declared order."""
        outputs: list[Path] = []
        for action in sorted(plan, key=lambda item: int(item.get("order", 0))):
            operation = str(action.get("operation") or "")
            output = Path(action["output"])
            if operation == "copy":
                shutil.copy2(Path(action["source"]), output)
                outputs.append(output)
                continue
            cmd = self.build_conversion_command(action)
            await self._run_ffmpeg_command(cmd)
            if output.exists():
                outputs.append(output)
        return outputs

    async def _run_ffmpeg_command(self, cmd: list[str]) -> None:
        """Run FFmpeg command and raise FFmpegError on failure."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise FFmpegError(f"Conversion failed: {error_msg}")
        except Exception as e:
            raise FFmpegError(f"Conversion failed: {e}") from e

    async def _process_m4a(self, context: ProcessingContext) -> None:
        """Backward-compatible wrapper for M4A/M4B processing."""
        stage_dir = context.stage_dir
        if not stage_dir:
            raise FFmpegError("Stage directory not set")
        plan = self.plan_import_conversion(
            context.source,
            stage_dir,
            chapters=await self._detect_chapters(context.source),
        )
        context.converted_files.extend(await self._execute_plan(plan))

    async def _process_opus(self, context: ProcessingContext) -> None:
        """Backward-compatible wrapper for Opus processing."""
        stage_dir = context.stage_dir
        if not stage_dir:
            raise FFmpegError("Stage directory not set")
        plan = self.plan_import_conversion(context.source, stage_dir)
        context.converted_files.extend(await self._execute_plan(plan))

    async def _detect_chapters(self, path: Path) -> list[dict[str, Any]]:
        """Detect chapters using ffprobe."""
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_chapters",
            str(path),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _stderr = await proc.communicate()
            if proc.returncode != 0:
                return []
            data = json.loads(stdout.decode())
            chapters = data.get("chapters", [])
            if isinstance(chapters, list):
                return [chapter for chapter in chapters if isinstance(chapter, dict)]
            return []
        except Exception:
            return []

    async def _convert_to_mp3(self, source: Path, output: Path) -> None:
        """Backward-compatible single-file conversion wrapper."""
        action = {
            "operation": "convert",
            "source": source,
            "output": output,
            "loudnorm": self.loudnorm,
        }
        await self._run_ffmpeg_command(self.build_conversion_command(action))

    async def _split_by_chapters(
        self,
        source: Path,
        output_dir: Path,
        chapters: list[dict[str, Any]],
    ) -> list[Path]:
        """Backward-compatible chapter split wrapper."""
        plan = self._plan_split_actions(source, output_dir, chapters)
        return await self._execute_plan(plan)

    def _check_ffmpeg(self) -> bool:
        """Check if ffmpeg is available."""
        return shutil.which("ffmpeg") is not None
