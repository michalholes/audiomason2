"""Audio processing plugin - converts M4A/Opus to MP3.

Based on AM1 audio.py functionality.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path

from audiomason.core import ProcessingContext
from audiomason.core.errors import AudioMasonError


class FFmpegError(AudioMasonError):
    """FFmpeg operation failed."""

    pass


class AudioProcessorPlugin:
    """Audio processor plugin.

    Handles:
    - M4A → MP3 conversion
    - Opus → MP3 conversion
    - Chapter detection
    - Chapter splitting
    - Loudness normalization
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

        # Check FFmpeg availability
        if not self._check_ffmpeg():
            raise FFmpegError(
                "FFmpeg not found",
                "Install with: sudo apt-get install ffmpeg",
            )

        # Detect format
        fmt = source.suffix.lower()

        if fmt in [".m4a", ".m4b"]:
            await self._process_m4a(context)
        elif fmt == ".opus":
            await self._process_opus(context)
        elif fmt == ".mp3":
            # Already MP3, just copy
            context.add_warning("Source is already MP3, copying...")
            if context.stage_dir:
                output = context.stage_dir / source.name
                shutil.copy2(source, output)
                context.converted_files.append(output)
        else:
            raise FFmpegError(f"Unsupported format: {fmt}")

        return context

    async def _process_m4a(self, context: ProcessingContext) -> None:
        """Process M4A file.

        Args:
            context: Processing context
        """
        source = context.source
        stage_dir = context.stage_dir

        if not stage_dir:
            raise FFmpegError("Stage directory not set")

        # Check for chapters
        chapters = await self._detect_chapters(source)
        has_chapters = len(chapters) > 1

        context.add_warning(f"M4A file: {len(chapters)} chapter(s) detected")

        # Split by chapters if requested and available
        if self.split_chapters and has_chapters:
            outputs = await self._split_by_chapters(source, stage_dir, chapters)
            context.converted_files.extend(outputs)
            context.add_warning(f"Split into {len(outputs)} files")
        else:
            # Single file conversion
            output = stage_dir / f"{source.stem}.mp3"
            await self._convert_to_mp3(source, output)
            context.converted_files.append(output)

    async def _process_opus(self, context: ProcessingContext) -> None:
        """Process Opus file.

        Args:
            context: Processing context
        """
        source = context.source
        stage_dir = context.stage_dir

        if not stage_dir:
            raise FFmpegError("Stage directory not set")

        output = stage_dir / f"{source.stem}.mp3"
        await self._convert_to_mp3(source, output)
        context.converted_files.append(output)

    async def _detect_chapters(self, path: Path) -> list[dict]:
        """Detect chapters using ffprobe.

        Args:
            path: Audio file path

        Returns:
            List of chapter dicts with start_time, end_time
        """
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

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                return []

            data = json.loads(stdout.decode())
            return data.get("chapters", [])

        except Exception:
            return []

    async def _convert_to_mp3(self, source: Path, output: Path) -> None:
        """Convert audio file to MP3.

        Args:
            source: Source file
            output: Output file
        """
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vn",  # No video
        ]

        # Add loudnorm filter if requested
        if self.loudnorm:
            cmd.extend(["-af", "loudnorm=I=-16:LRA=11:TP=-1.5"])

        # Audio codec and quality
        cmd.extend(
            [
                "-codec:a",
                "libmp3lame",
                "-q:a",
                "4",  # VBR quality (0-9, 4 is good)
                "-b:a",
                self.bitrate,
                str(output),
            ]
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise FFmpegError(f"Conversion failed: {error_msg}")

        except Exception as e:
            raise FFmpegError(f"Conversion failed: {e}") from e

    async def _split_by_chapters(
        self, source: Path, output_dir: Path, chapters: list[dict]
    ) -> list[Path]:
        """Split M4A by chapters.

        Args:
            source: Source M4A file
            output_dir: Output directory
            chapters: Chapter list from ffprobe

        Returns:
            List of output MP3 files
        """
        if len(chapters) < 2:
            return []

        # Extract times
        times: list[tuple[float, float]] = []
        for ch in chapters:
            try:
                start = float(ch["start_time"])
                end = float(ch["end_time"])
                times.append((start, end))
            except Exception:
                return []

        # Create output files
        outputs = []

        for i, (start, end) in enumerate(times, 1):
            output = output_dir / f"{i:02d}.mp3"

            duration = end - start

            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-nostdin",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                str(start),
                "-i",
                str(source),
                "-t",
                str(duration),
                "-vn",
            ]

            if self.loudnorm:
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

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                await proc.communicate()

                if proc.returncode == 0 and output.exists():
                    outputs.append(output)

            except Exception:
                continue

        return outputs

    def _check_ffmpeg(self) -> bool:
        """Check if ffmpeg is available.

        Returns:
            True if available
        """
        return shutil.which("ffmpeg") is not None
