"""ID3 tagger plugin - write metadata to MP3 files using FFmpeg."""

from __future__ import annotations

import asyncio
from pathlib import Path

from audiomason.core import ProcessingContext
from audiomason.core.errors import AudioMasonError


class ID3Error(AudioMasonError):
    """ID3 tagging error."""

    pass


class ID3TaggerPlugin:
    """ID3 tagger plugin.

    Writes metadata tags to MP3 files using FFmpeg.
    Supports: title, artist, album, year, genre, track number.
    """

    def __init__(self, config: dict | None = None) -> None:
        """Initialize plugin.

        Args:
            config: Plugin configuration
        """
        self.config = config or {}

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        """Write ID3 tags to converted MP3 files.

        Args:
            context: Processing context

        Returns:
            Updated context
        """
        if not context.converted_files:
            context.add_warning("No MP3 files to tag")
            return context

        # Tag each converted file
        for mp3_file in context.converted_files:
            if mp3_file.suffix.lower() == ".mp3":
                await self._tag_file(mp3_file, context)

        context.add_warning(f"Tagged {len(context.converted_files)} file(s)")
        return context

    async def _tag_file(self, mp3_file: Path, context: ProcessingContext) -> None:
        """Tag a single MP3 file.

        Args:
            mp3_file: MP3 file to tag
            context: Processing context with metadata
        """
        # Build metadata dict
        metadata = {}

        if context.title:
            metadata["title"] = context.title
        if context.author:
            metadata["artist"] = context.author
            metadata["album_artist"] = context.author
        if context.year:
            metadata["date"] = str(context.year)
        if context.genre:
            metadata["genre"] = context.genre
        if context.narrator:
            metadata["composer"] = context.narrator  # Use composer for narrator

        # Album is usually same as title for audiobooks
        if context.title:
            metadata["album"] = context.title

        # Series info in comment
        if context.series and context.series_number:
            metadata["comment"] = f"{context.series} #{context.series_number}"
        elif context.series:
            metadata["comment"] = context.series

        if not metadata:
            return

        # Create temporary file for tagging
        temp_file = mp3_file.with_suffix(".tagged.mp3")

        # Build FFmpeg command
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(mp3_file),
            "-c",
            "copy",  # Copy streams without re-encoding
        ]

        # Add metadata tags
        for key, value in metadata.items():
            cmd.extend(["-metadata", f"{key}={value}"])

        cmd.append(str(temp_file))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise ID3Error(f"Tagging failed: {error_msg}")

            # Replace original with tagged version
            temp_file.replace(mp3_file)

        except Exception as e:
            if temp_file.exists():
                temp_file.unlink()
            raise ID3Error(f"Failed to tag {mp3_file.name}: {e}") from e

    async def read_tags(self, mp3_file: Path) -> dict[str, str]:
        """Read existing ID3 tags from MP3 file.

        Args:
            mp3_file: MP3 file

        Returns:
            Dict of metadata tags
        """
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format_tags",
            "-of",
            "default=noprint_wrappers=1",
            str(mp3_file),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                return {}

            # Parse output: TAG:key=value
            metadata = {}
            for line in stdout.decode().split("\n"):
                if line.startswith("TAG:"):
                    line = line[4:]  # Remove "TAG:" prefix
                    if "=" in line:
                        key, value = line.split("=", 1)
                        metadata[key.lower()] = value

            return metadata

        except Exception:
            return {}
