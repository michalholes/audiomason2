"""ID3 tagger plugin - write metadata to MP3 files using FFmpeg."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from audiomason.core import ProcessingContext
from audiomason.core.errors import AudioMasonError


class ID3Error(AudioMasonError):
    """ID3 tagging error."""

    pass


_TAG_ORDER = (
    "title",
    "artist",
    "album",
    "album_artist",
    "date",
    "genre",
    "composer",
    "comment",
    "track",
)
_CANONICAL_FIELD_KEYS = ("title", "artist", "album", "album_artist")
_RESERVED_TAG_KEYS = {
    "field_map",
    "preserve_cover",
    "track_start",
    "values",
    "wipe_before_write",
}


class ID3TaggerPlugin:
    """ID3 tagger plugin.

    Writes metadata tags to MP3 files using FFmpeg.
    Supports deterministic wipe-before-write semantics for import runtime.
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

        tags = self.build_context_tags(context)
        if not tags:
            return context

        tag_payload: dict[str, Any] = dict(tags)
        track_start = getattr(context, "track_start", None)
        if track_start is not None:
            tag_payload["track_start"] = track_start

        tagged_count = 0
        for file_index, mp3_file in enumerate(context.converted_files):
            if mp3_file.suffix.lower() != ".mp3":
                continue
            await self.write_tags(mp3_file, tag_payload, file_index=file_index)
            tagged_count += 1

        context.add_warning(f"Tagged {tagged_count} file(s)")
        return context

    def build_context_tags(self, context: ProcessingContext) -> dict[str, str]:
        """Build canonical ID3 tags from ProcessingContext."""
        values: dict[str, str] = {}

        def add(key: str, value: Any) -> None:
            text = str(value).strip() if value is not None else ""
            if text:
                values[key] = text

        add("title", context.title)
        add("artist", context.author)
        add("album", context.title)
        add("album_artist", context.author)
        add("date", context.year)
        add("genre", context.genre)
        add("composer", context.narrator)
        if context.series and context.series_number is not None:
            add("comment", f"{context.series} #{context.series_number}")
        elif context.series:
            add("comment", context.series)

        return self._ordered_tags(values)

    def build_write_tags_command(
        self,
        mp3_file: Path,
        output_file: Path,
        tags: dict[str, Any],
        *,
        wipe_before_write: bool = True,
        preserve_cover: bool = True,
        file_index: int = 0,
    ) -> list[str]:
        """Build deterministic FFmpeg command for wipe-before-write tagging."""
        ordered_tags = self._normalize_tag_payload(tags, file_index=file_index)
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(mp3_file),
            "-map",
            "0" if preserve_cover else "0:a:0",
        ]
        if wipe_before_write:
            cmd.extend(["-map_metadata", "-1"])
        cmd.extend(["-c", "copy", "-id3v2_version", "3"])
        for key, value in ordered_tags.items():
            cmd.extend(["-metadata", f"{key}={value}"])
        cmd.append(str(output_file))
        return cmd

    async def write_tags(
        self,
        mp3_file: Path,
        tags: dict[str, Any],
        *,
        wipe_before_write: bool = True,
        preserve_cover: bool = True,
        file_index: int = 0,
    ) -> None:
        """Write canonical tags to a single MP3 file."""
        ordered_tags = self._normalize_tag_payload(tags, file_index=file_index)
        if not ordered_tags:
            return

        temp_file = mp3_file.with_suffix(".tagged.mp3")
        cmd = self.build_write_tags_command(
            mp3_file,
            temp_file,
            ordered_tags,
            wipe_before_write=wipe_before_write,
            preserve_cover=preserve_cover,
            file_index=file_index,
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise ID3Error(f"Tagging failed: {error_msg}")
            temp_file.replace(mp3_file)
        except Exception as e:
            if temp_file.exists():
                temp_file.unlink()
            raise ID3Error(f"Failed to tag {mp3_file.name}: {e}") from e

    def _ordered_tags(self, tags: dict[str, str]) -> dict[str, str]:
        """Return tags in canonical write order."""
        ordered: dict[str, str] = {}
        for key in _TAG_ORDER:
            value = str(tags.get(key) or "").strip()
            if value:
                ordered[key] = value
        extra_keys = sorted(key for key in tags if key not in _TAG_ORDER)
        for key in extra_keys:
            value = str(tags.get(key) or "").strip()
            if value:
                ordered[key] = value
        return ordered

    def build_capability_tags(
        self,
        capability: dict[str, Any],
        *,
        file_index: int = 0,
    ) -> dict[str, str]:
        """Resolve a metadata.tags capability into canonical ID3 tags."""
        values_any = capability.get("values")
        values = dict(values_any) if isinstance(values_any, dict) else {}
        if "track_start" in capability and "track_start" not in values:
            values["track_start"] = capability.get("track_start")
        field_map_any = capability.get("field_map")
        field_map = dict(field_map_any) if isinstance(field_map_any, dict) else {}
        return self._build_mapped_tags(values, field_map=field_map, file_index=file_index)

    def _normalize_tag_payload(
        self,
        payload: dict[str, Any],
        *,
        file_index: int = 0,
    ) -> dict[str, str]:
        if any(key in payload for key in ("field_map", "values", "track_start")):
            return self.build_capability_tags(payload, file_index=file_index)
        return self._build_mapped_tags(payload, file_index=file_index)

    def _build_mapped_tags(
        self,
        values: dict[str, Any],
        *,
        field_map: dict[str, Any] | None = None,
        file_index: int = 0,
    ) -> dict[str, str]:
        cleaned: dict[str, str] = {}
        for key, value in values.items():
            text = str(value).strip() if value is not None else ""
            if text:
                cleaned[str(key)] = text

        raw_field_map = field_map or {}
        mapped_sources = {
            str(source).strip() for source in raw_field_map.values() if str(source).strip()
        }
        tags: dict[str, str] = {}
        for target in _CANONICAL_FIELD_KEYS:
            mapped_source = str(raw_field_map.get(target) or "").strip()
            value = ""
            if mapped_source:
                value = cleaned.get(mapped_source, "")
            if not value:
                value = cleaned.get(target, "")
            if value:
                tags[target] = value

        track_value = cleaned.get("track", "")
        if not track_value:
            track_start = self._parse_track_start(cleaned.get("track_start"))
            if track_start is not None:
                track_value = str(track_start + file_index)
        if track_value:
            tags["track"] = track_value

        for key, value in cleaned.items():
            if (
                key in _CANONICAL_FIELD_KEYS
                or key == "track"
                or key in _RESERVED_TAG_KEYS
                or key in mapped_sources
            ):
                continue
            tags[key] = value
        return self._ordered_tags(tags)

    def _parse_track_start(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    async def _tag_file(self, mp3_file: Path, context: ProcessingContext) -> None:
        """Backward-compatible wrapper for context-based tagging."""
        await self.write_tags(mp3_file, self.build_context_tags(context))

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

            stdout, _stderr = await proc.communicate()

            if proc.returncode != 0:
                return {}

            metadata = {}
            for line in stdout.decode().split("\n"):
                if line.startswith("TAG:"):
                    line = line[4:]
                    if "=" in line:
                        key, value = line.split("=", 1)
                        metadata[key.lower()] = value

            return metadata

        except Exception:
            return {}
