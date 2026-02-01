"""Synchronous Cover Handler Plugin - extract, download, embed cover art."""

from __future__ import annotations

import urllib.request
from pathlib import Path

try:
    from mutagen.id3 import APIC, ID3
    from mutagen.mp3 import MP3

    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

from audiomason.core import ProcessingContext
from audiomason.core.errors import AudioMasonError


class CoverError(AudioMasonError):
    """Cover handling error."""

    pass


class CoverHandlerSync:
    """Synchronous cover art handler.

    Handles:
    - Extracting cover from MP3 files
    - Finding cover files in directories
    - Downloading cover from URL
    - Saving cover to file
    """

    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

    def __init__(self, config: dict | None = None) -> None:
        """Initialize plugin.

        Args:
            config: Plugin configuration
        """
        self.config = config or {}
        self.verbosity = self.config.get("verbosity", 1)
        self.default_cover_name = self.config.get("default_cover_name", "cover.jpg")

    def _log_debug(self, msg: str) -> None:
        """Log debug message (verbosity >= 3)."""
        if self.verbosity >= 3:
            print(f"[DEBUG] [cover_handler_sync] {msg}")

    def _log_verbose(self, msg: str) -> None:
        """Log verbose message (verbosity >= 2)."""
        if self.verbosity >= 2:
            print(f"[VERBOSE] [cover_handler_sync] {msg}")

    def _log_info(self, msg: str) -> None:
        """Log info message (verbosity >= 1)."""
        if self.verbosity >= 1:
            print(f"[cover_handler_sync] {msg}")

    def _log_error(self, msg: str) -> None:
        """Log error message (always shown)."""
        print(f"[ERROR] [cover_handler_sync] {msg}")

    def find_cover_in_directory(self, directory: Path) -> Path | None:
        """Find cover image file in directory.

        Args:
            directory: Directory to search

        Returns:
            Path to cover file or None
        """
        self._log_debug(f"Searching for cover in: {directory}")

        if not directory.exists() or not directory.is_dir():
            return None

        # Look for common cover filenames
        common_names = [
            "cover.jpg",
            "cover.jpeg",
            "cover.png",
            "folder.jpg",
            "folder.jpeg",
            "folder.png",
            "front.jpg",
            "front.jpeg",
            "front.png",
            "albumart.jpg",
            "albumart.jpeg",
            "albumart.png",
        ]

        for name in common_names:
            cover_path = directory / name
            if cover_path.exists():
                self._log_verbose(f"Found cover: {cover_path.name}")
                return cover_path

        # Look for any image file
        for item in directory.iterdir():
            if item.is_file() and item.suffix.lower() in self.IMAGE_EXTS:
                self._log_verbose(f"Found image: {item.name}")
                return item

        self._log_debug("No cover found in directory")
        return None

    def extract_cover_from_mp3(self, mp3_file: Path, output_path: Path) -> Path | None:
        """Extract embedded cover art from MP3 file.

        Args:
            mp3_file: MP3 file to extract from
            output_path: Path to save extracted cover

        Returns:
            Path to extracted cover or None

        Raises:
            CoverError: If extraction fails
        """
        if not MUTAGEN_AVAILABLE:
            raise CoverError("mutagen library not installed")

        if not mp3_file.exists():
            raise CoverError(f"MP3 file not found: {mp3_file}")

        self._log_debug(f"Extracting cover from: {mp3_file.name}")

        try:
            audio = MP3(str(mp3_file), ID3=ID3)

            # Look for APIC frame (cover art)
            for tag in audio.tags.values():
                if isinstance(tag, APIC):
                    self._log_verbose(f"Found embedded cover: {tag.desc}")

                    # Write cover data to file
                    with open(output_path, "wb") as f:
                        f.write(tag.data)

                    self._log_info(f"Extracted cover to: {output_path.name}")
                    return output_path

            self._log_debug("No embedded cover found")
            return None

        except Exception as e:
            raise CoverError(f"Failed to extract cover: {e}") from e

    def download_cover(self, url: str, output_path: Path) -> Path | None:
        """Download cover image from URL.

        Args:
            url: Cover image URL
            output_path: Path to save downloaded cover

        Returns:
            Path to downloaded cover or None

        Raises:
            CoverError: If download fails
        """
        self._log_info(f"Downloading cover from: {url}")

        try:
            # Download image
            with urllib.request.urlopen(url, timeout=10) as response:
                cover_data = response.read()

            # Save to file
            with open(output_path, "wb") as f:
                f.write(cover_data)

            self._log_verbose(f"Downloaded cover to: {output_path.name}")
            return output_path

        except Exception as e:
            raise CoverError(f"Failed to download cover: {e}") from e

    def find_or_extract_cover(self, context: ProcessingContext) -> Path | None:
        """Find cover in directory or extract from MP3.

        Args:
            context: Processing context

        Returns:
            Path to cover file or None
        """
        if not hasattr(context, "stage_dir") or not context.stage_dir:
            self._log_verbose("No stage directory in context")
            return None

        stage_dir = context.stage_dir

        # First, look for cover file in directory
        cover_path = self.find_cover_in_directory(stage_dir)

        if cover_path:
            self._log_info(f"Using cover file: {cover_path.name}")
            return cover_path

        # If no file found, try to extract from first MP3
        if hasattr(context, "converted_files") and context.converted_files:
            for mp3_file in context.converted_files:
                if mp3_file.suffix.lower() == ".mp3":
                    output_path = stage_dir / self.default_cover_name

                    try:
                        extracted = self.extract_cover_from_mp3(mp3_file, output_path)
                        if extracted:
                            return extracted
                    except CoverError as e:
                        self._log_verbose(str(e))
                        continue

        self._log_verbose("No cover found")
        return None

    def process(self, context: ProcessingContext) -> ProcessingContext:
        """Main processing method (IProcessor interface).

        Finds cover and adds to context.

        Args:
            context: Processing context

        Returns:
            Updated context with cover_path
        """
        cover_path = self.find_or_extract_cover(context)

        if cover_path:
            context.cover_path = cover_path
            self._log_info(f"Cover ready: {cover_path.name}")
        else:
            self._log_verbose("No cover available")

        return context
