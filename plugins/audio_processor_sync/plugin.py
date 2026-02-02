"""Synchronous Audio Processor Plugin - FFmpeg operations."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from audiomason.core import ProcessingContext
from audiomason.core.errors import AudioMasonError


class AudioProcessingError(AudioMasonError):
    """Audio processing error."""

    pass


@dataclass
class ChapterInfo:
    """Chapter information from audio file."""

    id: int
    start_time: float
    end_time: float
    title: str | None = None


class AudioProcessorSync:
    """Synchronous audio processor using FFmpeg.

    Handles:
    - Format conversion (M4A/Opus -> MP3)
    - Chapter detection
    - Chapter splitting
    - Loudness normalization
    - Format detection
    """

    SUPPORTED_FORMATS = {".m4a", ".m4b", ".opus", ".ogg", ".flac", ".wav", ".mp3"}

    def __init__(self, config: dict | None = None) -> None:
        """Initialize plugin.

        Args:
            config: Plugin configuration
        """
        self.config = config or {}
        self.verbosity = self.config.get("verbosity", 1)

        # FFmpeg paths
        self.ffmpeg = self.config.get("ffmpeg_path", "ffmpeg")
        self.ffprobe = self.config.get("ffprobe_path", "ffprobe")

        # Audio settings
        self.bitrate = self.config.get("bitrate", "128k")
        self.target_format = self.config.get("target_format", "mp3")
        self.loudnorm = self.config.get("loudnorm", False)
        self.split_chapters = self.config.get("split_chapters", False)
        self.loglevel = self.config.get("loglevel", "warning")

    def _log_debug(self, msg: str) -> None:
        """Log debug message (verbosity >= 3)."""
        if self.verbosity >= 3:
            print(f"[DEBUG] [audio_processor_sync] {msg}")

    def _log_verbose(self, msg: str) -> None:
        """Log verbose message (verbosity >= 2)."""
        if self.verbosity >= 2:
            print(f"[VERBOSE] [audio_processor_sync] {msg}")

    def _log_info(self, msg: str) -> None:
        """Log info message (verbosity >= 1)."""
        if self.verbosity >= 1:
            print(f"[audio_processor_sync] {msg}")

    def _log_error(self, msg: str) -> None:
        """Log error message (always shown)."""
        print(f"[ERROR] [audio_processor_sync] {msg}")

    def detect_format(self, audio_file: Path) -> dict:
        """Detect audio format using ffprobe.

        Args:
            audio_file: Audio file path

        Returns:
            Format information dictionary

        Raises:
            AudioProcessingError: If detection fails
        """
        self._log_debug(f"Detecting format: {audio_file}")

        cmd = [
            self.ffprobe,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(audio_file),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)

            format_info = {
                "format_name": data.get("format", {}).get("format_name", "unknown"),
                "duration": float(data.get("format", {}).get("duration", 0)),
                "bit_rate": data.get("format", {}).get("bit_rate", "unknown"),
                "codec": "unknown",
            }

            # Get audio codec from first audio stream
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "audio":
                    format_info["codec"] = stream.get("codec_name", "unknown")
                    break

            self._log_verbose(
                f"Format: {format_info['format_name']}, Codec: {format_info['codec']}"
            )
            return format_info

        except subprocess.CalledProcessError as e:
            raise AudioProcessingError(f"Format detection failed: {e.stderr}") from e
        except json.JSONDecodeError as e:
            raise AudioProcessingError(f"Failed to parse ffprobe output: {e}") from e

    def detect_chapters(self, audio_file: Path) -> list[ChapterInfo]:
        """Detect chapters in audio file.

        Args:
            audio_file: Audio file path

        Returns:
            List of chapter information
        """
        self._log_debug(f"Detecting chapters: {audio_file}")

        cmd = [
            self.ffprobe,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_chapters",
            str(audio_file),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)

            chapters = []
            for idx, ch in enumerate(data.get("chapters", [])):
                chapter = ChapterInfo(
                    id=idx,
                    start_time=float(ch.get("start_time", 0)),
                    end_time=float(ch.get("end_time", 0)),
                    title=ch.get("tags", {}).get("title"),
                )
                chapters.append(chapter)

            self._log_info(f"Found {len(chapters)} chapter(s)")
            return chapters

        except subprocess.CalledProcessError as e:
            self._log_verbose(f"Chapter detection failed: {e.stderr}")
            return []
        except json.JSONDecodeError:
            self._log_verbose("Failed to parse chapter data")
            return []

    def convert(
        self,
        input_file: Path,
        output_file: Path,
        bitrate: str | None = None,
        loudnorm: bool | None = None,
    ) -> Path:
        """Convert audio file to target format.

        Args:
            input_file: Input audio file
            output_file: Output audio file
            bitrate: Target bitrate (overrides config)
            loudnorm: Enable loudness normalization (overrides config)

        Returns:
            Path to converted file

        Raises:
            AudioProcessingError: If conversion fails
        """
        bitrate = bitrate or self.bitrate
        loudnorm = loudnorm if loudnorm is not None else self.loudnorm

        self._log_info(f"Converting: {input_file.name} -> {output_file.name}")
        self._log_verbose(f"Bitrate: {bitrate}, Loudnorm: {loudnorm}")

        # Build FFmpeg command
        cmd = [
            self.ffmpeg,
            "-i",
            str(input_file),
            "-vn",  # No video
            "-map_metadata",
            "0",  # Copy metadata
        ]

        # Audio filters
        filters = []
        if loudnorm:
            filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")

        if filters:
            cmd.extend(["-af", ",".join(filters)])

        # Audio codec and bitrate
        cmd.extend(
            [
                "-codec:a",
                "libmp3lame",
                "-b:a",
                bitrate,
                "-q:a",
                "2",  # VBR quality
            ]
        )

        # Output options
        cmd.extend(
            [
                "-loglevel",
                self.loglevel,
                "-y",  # Overwrite output
                str(output_file),
            ]
        )

        # Log command in debug mode
        if self.verbosity >= 3:
            self._log_debug(f"FFmpeg command: {' '.join(cmd)}")

        try:
            # Run FFmpeg
            if self.verbosity >= 3:
                # Show FFmpeg output in debug mode
                subprocess.run(cmd, check=True, text=True)
            else:
                # Suppress FFmpeg output
                subprocess.run(cmd, capture_output=True, text=True, check=True)

            if not output_file.exists():
                raise AudioProcessingError("Output file not created")

            self._log_verbose(f"Conversion complete: {output_file.name}")
            return output_file

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if hasattr(e, "stderr") and e.stderr else str(e)
            raise AudioProcessingError(f"Conversion failed: {error_msg}") from e

    def split_by_chapters(
        self,
        input_file: Path,
        output_dir: Path,
        chapters: list[ChapterInfo],
        bitrate: str | None = None,
    ) -> list[Path]:
        """Split audio file by chapters.

        Args:
            input_file: Input audio file
            output_dir: Output directory for chapters
            chapters: List of chapter information
            bitrate: Target bitrate (overrides config)

        Returns:
            List of created chapter files

        Raises:
            AudioProcessingError: If splitting fails
        """
        if not chapters:
            self._log_verbose("No chapters to split")
            return []

        bitrate = bitrate or self.bitrate

        self._log_info(f"Splitting into {len(chapters)} chapter(s)")
        output_dir.mkdir(parents=True, exist_ok=True)

        output_files = []

        for chapter in chapters:
            # Generate chapter filename
            chapter_num = chapter.id + 1
            title = chapter.title or f"Chapter {chapter_num}"

            # Sanitize title
            safe_title = self._sanitize_filename(title)
            output_file = output_dir / f"{chapter_num:02d} - {safe_title}.mp3"

            self._log_verbose(f"Extracting chapter {chapter_num}: {title}")

            # Calculate duration
            duration = chapter.end_time - chapter.start_time

            # Build FFmpeg command for chapter extraction
            cmd = [
                self.ffmpeg,
                "-i",
                str(input_file),
                "-ss",
                str(chapter.start_time),
                "-t",
                str(duration),
                "-vn",
                "-codec:a",
                "libmp3lame",
                "-b:a",
                bitrate,
                "-q:a",
                "2",
                "-loglevel",
                self.loglevel,
                "-y",
                str(output_file),
            ]

            if self.verbosity >= 3:
                self._log_debug(f"Chapter {chapter_num} command: {' '.join(cmd)}")

            try:
                subprocess.run(cmd, capture_output=True, text=True, check=True)

                if output_file.exists():
                    output_files.append(output_file)
                    self._log_debug(f"Created: {output_file.name}")
                else:
                    self._log_error(f"Chapter file not created: {output_file.name}")

            except subprocess.CalledProcessError as e:
                self._log_error(f"Chapter {chapter_num} extraction failed: {e.stderr}")
                continue

        self._log_info(f"Created {len(output_files)} chapter file(s)")
        return output_files

    def process_files(self, context: ProcessingContext) -> ProcessingContext:
        """Process all audio files in stage directory.

        Args:
            context: Processing context

        Returns:
            Updated context with converted_files

        Raises:
            AudioProcessingError: If processing fails
        """
        if not hasattr(context, "stage_dir") or not context.stage_dir:
            raise AudioProcessingError("No stage directory in context")

        stage_dir = context.stage_dir

        # Debug: show what we're looking for
        self._log_debug(f"Looking for audio files in: {stage_dir}")
        self._log_debug(f"Stage dir exists: {stage_dir.exists()}")
        if stage_dir.exists():
            all_files = list(stage_dir.rglob("*"))
            self._log_debug(f"Total files in stage: {len([f for f in all_files if f.is_file()])}")

        # Find all audio files
        audio_files = []
        for ext in self.SUPPORTED_FORMATS:
            found = list(stage_dir.rglob(f"*{ext}"))
            if found:
                self._log_debug(f"Pattern '*{ext}': found {len(found)} files")
            audio_files.extend(found)

        if not audio_files:
            raise AudioProcessingError(f"No audio files found in {stage_dir}")

        self._log_info(f"Found {len(audio_files)} audio file(s) to process")

        converted_files = []

        for audio_file in sorted(audio_files):
            self._log_verbose(f"Processing: {audio_file.name}")

            # Check if chapter splitting requested
            if self.split_chapters:
                chapters = self.detect_chapters(audio_file)

                if chapters:
                    # Create chapters subdirectory
                    chapters_dir = stage_dir / "chapters"
                    chapter_files = self.split_by_chapters(
                        audio_file, chapters_dir, chapters, self.bitrate
                    )
                    converted_files.extend(chapter_files)
                    continue

            # Single file conversion
            output_file = audio_file.with_suffix(".mp3")

            # If already MP3, skip or re-encode based on settings
            if audio_file.suffix.lower() == ".mp3":
                if self.loudnorm:
                    # Re-encode with loudnorm
                    temp_output = stage_dir / f"temp_{output_file.name}"
                    self.convert(audio_file, temp_output, self.bitrate, True)
                    audio_file.unlink()
                    temp_output.rename(output_file)
                    converted_files.append(output_file)
                else:
                    # Use as-is
                    converted_files.append(audio_file)
            else:
                # Convert to MP3
                self.convert(audio_file, output_file, self.bitrate, self.loudnorm)

                # Remove original if conversion successful
                if output_file.exists():
                    audio_file.unlink()
                    converted_files.append(output_file)

        context.converted_files = converted_files
        self._log_info(f"Processing complete: {len(converted_files)} file(s)")

        return context

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Sanitize filename for filesystem.

        Args:
            name: Original name

        Returns:
            Sanitized name
        """
        replacements = {
            "/": "-",
            "\\": "-",
            ":": "-",
            "*": "",
            "?": "",
            '"': "",
            "<": "",
            ">": "",
            "|": "",
        }

        result = name
        for old, new in replacements.items():
            result = result.replace(old, new)

        result = " ".join(result.split())
        return result.strip()

    def process(self, context: ProcessingContext) -> ProcessingContext:
        """Main processing method (IProcessor interface).

        Args:
            context: Processing context

        Returns:
            Updated context
        """
        return self.process_files(context)
