"""Synchronous ID3 Tagger Plugin - write metadata to MP3 files."""

from __future__ import annotations

from pathlib import Path

try:
    from mutagen.id3 import APIC, ID3, TALB, TDRC, TIT2, TPE1, TPE2, TRCK
    from mutagen.mp3 import MP3

    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

from audiomason.core import ProcessingContext
from audiomason.core.errors import AudioMasonError


class TaggingError(AudioMasonError):
    """ID3 tagging error."""

    pass


class ID3TaggerSync:
    """Synchronous ID3 tagger using mutagen.

    Handles:
    - Writing ID3v2.4 tags
    - Optional tag wiping
    - Cover art embedding
    - Chapter metadata
    """

    def __init__(self, config: dict | None = None) -> None:
        """Initialize plugin.

        Args:
            config: Plugin configuration

        Raises:
            TaggingError: If mutagen not available
        """
        if not MUTAGEN_AVAILABLE:
            raise TaggingError("mutagen library not installed. Install with: pip install mutagen")

        self.config = config or {}
        self.verbosity = self.config.get("verbosity", 1)
        self.wipe_before_tagging = self.config.get("wipe_before_tagging", False)

    def _log_debug(self, msg: str) -> None:
        """Log debug message (verbosity >= 3)."""
        if self.verbosity >= 3:
            print(f"[DEBUG] [id3_tagger_sync] {msg}")

    def _log_verbose(self, msg: str) -> None:
        """Log verbose message (verbosity >= 2)."""
        if self.verbosity >= 2:
            print(f"[VERBOSE] [id3_tagger_sync] {msg}")

    def _log_info(self, msg: str) -> None:
        """Log info message (verbosity >= 1)."""
        if self.verbosity >= 1:
            print(f"[id3_tagger_sync] {msg}")

    def _log_error(self, msg: str) -> None:
        """Log error message (always shown)."""
        print(f"[ERROR] [id3_tagger_sync] {msg}")

    def tag_file(
        self,
        mp3_file: Path,
        title: str | None = None,
        artist: str | None = None,
        album: str | None = None,
        year: int | None = None,
        track_number: int | None = None,
        total_tracks: int | None = None,
        album_artist: str | None = None,
        cover_path: Path | None = None,
    ) -> None:
        """Tag single MP3 file with metadata.

        Args:
            mp3_file: MP3 file to tag
            title: Track title
            artist: Artist name
            album: Album name
            year: Release year
            track_number: Track number
            total_tracks: Total number of tracks
            album_artist: Album artist
            cover_path: Path to cover image

        Raises:
            TaggingError: If tagging fails
        """
        if not mp3_file.exists():
            raise TaggingError(f"MP3 file not found: {mp3_file}")

        self._log_verbose(f"Tagging: {mp3_file.name}")

        try:
            # Load or create ID3 tags
            try:
                audio = MP3(str(mp3_file), ID3=ID3)

                if self.wipe_before_tagging:
                    self._log_debug("Wiping existing tags")
                    audio.delete()
                    audio = MP3(str(mp3_file), ID3=ID3)
                    audio.add_tags()

            except Exception:
                # File has no tags, create new
                audio = MP3(str(mp3_file), ID3=ID3)
                audio.add_tags()

            # Set tags
            if audio.tags is None:
                audio.add_tags()
            
            # Now audio.tags should not be None, but mypy needs explicit check
            assert audio.tags is not None
            
            if title:
                audio.tags["TIT2"] = TIT2(encoding=3, text=title)
                self._log_debug(f"Title: {title}")

            if artist:
                audio.tags["TPE1"] = TPE1(encoding=3, text=artist)
                self._log_debug(f"Artist: {artist}")

            if album:
                audio.tags["TALB"] = TALB(encoding=3, text=album)
                self._log_debug(f"Album: {album}")

            if year:
                audio.tags["TDRC"] = TDRC(encoding=3, text=str(year))
                self._log_debug(f"Year: {year}")

            if track_number:
                track_text = f"{track_number}/{total_tracks}" if total_tracks else str(track_number)
                audio.tags["TRCK"] = TRCK(encoding=3, text=track_text)
                self._log_debug(f"Track: {track_text}")

            if album_artist:
                audio.tags["TPE2"] = TPE2(encoding=3, text=album_artist)
                self._log_debug(f"Album artist: {album_artist}")

            # Embed cover art
            if cover_path and cover_path.exists():
                self._embed_cover(audio, cover_path)

            # Save tags
            audio.save(v2_version=4)
            self._log_debug("Tags saved")

        except Exception as e:
            raise TaggingError(f"Failed to tag {mp3_file.name}: {e}") from e

    def _embed_cover(self, audio: MP3, cover_path: Path) -> None:
        """Embed cover art into MP3 file.

        Args:
            audio: MP3 audio object
            cover_path: Path to cover image
        """
        self._log_debug(f"Embedding cover: {cover_path.name}")

        # Detect image MIME type
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
        }

        mime = mime_types.get(cover_path.suffix.lower(), "image/jpeg")

        with open(cover_path, "rb") as f:
            cover_data = f.read()

        # APIC frame for cover art
        if audio.tags is None:
            audio.add_tags()
        
        # Now audio.tags should not be None
        assert audio.tags is not None
        
        audio.tags["APIC"] = APIC(
            encoding=3,
            mime=mime,
            type=3,  # Cover (front)
            desc="Cover",
            data=cover_data,
        )

    def tag_files(self, context: ProcessingContext) -> ProcessingContext:
        """Tag all converted MP3 files with metadata from context.

        Args:
            context: Processing context

        Returns:
            Updated context

        Raises:
            TaggingError: If tagging fails
        """
        if not hasattr(context, "converted_files") or not context.converted_files:
            self._log_verbose("No converted files to tag")
            return context

        # Get metadata from context
        artist = getattr(context, "author", None) or getattr(context, "artist", None)
        album = getattr(context, "title", None) or getattr(context, "album", None)
        year = getattr(context, "year", None)
        cover_path = getattr(context, "cover_path", None)

        if not artist or not album:
            self._log_verbose("Missing artist or album metadata, skipping tagging")
            return context

        files = context.converted_files
        total_files = len(files)

        self._log_info(f"Tagging {total_files} file(s)")
        self._log_verbose(f"Artist: {artist}, Album: {album}")

        for idx, mp3_file in enumerate(sorted(files), 1):
            if mp3_file.suffix.lower() != ".mp3":
                self._log_debug(f"Skipping non-MP3: {mp3_file.name}")
                continue

            # Generate title from filename if not in context
            title = mp3_file.stem

            # Tag file
            try:
                self.tag_file(
                    mp3_file=mp3_file,
                    title=title,
                    artist=artist,
                    album=album,
                    year=year,
                    track_number=idx,
                    total_tracks=total_files,
                    album_artist=artist,
                    cover_path=cover_path,
                )
            except TaggingError as e:
                self._log_error(str(e))
                continue

        self._log_info("Tagging complete")
        return context

    def process(self, context: ProcessingContext) -> ProcessingContext:
        """Main processing method (IProcessor interface).

        Args:
            context: Processing context

        Returns:
            Updated context
        """
        return self.tag_files(context)
