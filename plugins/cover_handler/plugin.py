"""Cover handler plugin - based on AM1 covers.py.

Handles all cover operations:
- Extract from MP3/M4A
- Download from URL
- Convert image formats
- Embed into MP3
- Find file covers
"""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from audiomason.core import CoverChoice, ProcessingContext
from audiomason.core.errors import CoverError
from audiomason.core.logging import get_logger

logger = get_logger(__name__)

_FILE_COVER_NAMES = (
    "cover.jpg",
    "cover.jpeg",
    "cover.png",
    "cover.webp",
    "folder.jpg",
    "folder.jpeg",
    "folder.png",
    "front.jpg",
    "front.png",
)

_GENERIC_COVER_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
_EMBEDDED_SUFFIXES = {".mp3", ".m4a", ".m4b"}


def _cache_token(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


class CoverHandlerPlugin:
    """Cover handler plugin."""

    def __init__(self, config: dict | None = None) -> None:
        """Initialize plugin.

        Args:
            config: Plugin configuration
        """
        self.config = config or {}
        self.cover_size = self.config.get("cover_size", 1400)

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        """Handle cover based on user choice.

        Args:
            context: Processing context

        Returns:
            Updated context with cover
        """
        if context.cover_choice == CoverChoice.SKIP:
            context.add_warning("Skipping cover (user choice)")
            return context

        cover_path: Path | None = None

        try:
            candidates = self.discover_cover_candidates(
                context.source.parent,
                audio_file=context.source,
            )

            if context.cover_choice == CoverChoice.EMBEDDED:
                candidate = next(
                    (item for item in candidates if item.get("kind") == "embedded"),
                    None,
                )
                if candidate is not None:
                    cover_path = await self.apply_cover_candidate(candidate)

            elif context.cover_choice == CoverChoice.FILE:
                candidate = next(
                    (item for item in candidates if item.get("kind") == "file"),
                    None,
                )
                if candidate is not None:
                    file_output_dir = context.stage_dir if context.stage_dir is not None else None
                    cover_path = await self.apply_cover_candidate(
                        candidate,
                        output_dir=file_output_dir,
                    )

            elif context.cover_choice == CoverChoice.URL and context.cover_url:
                candidate = self.build_url_candidate(
                    context.cover_url,
                    stage_root="stage" if context.stage_dir is not None else None,
                )
                cover_path = await self.apply_cover_candidate(
                    candidate,
                    output_dir=context.stage_dir,
                )

            if cover_path and cover_path.exists():
                cover_path = await self.convert_to_jpeg(cover_path)
                context.cover_path = cover_path
                context.add_warning(f"Cover: {cover_path.name}")
            else:
                context.add_warning("Cover not found")

        except Exception as e:
            context.add_warning(f"Cover error: {e}")

        return context

    @staticmethod
    def _resolve_root_name(*, group_root: str | None, stage_root: str | None) -> str:
        root_name = str(group_root or "").strip()
        if root_name:
            return root_name
        return str(stage_root or "").strip()

    @staticmethod
    def _normalize_mime_type(mime_type: str | None) -> str:
        value = str(mime_type or "").split(";", 1)[0].strip().lower()
        return value

    def resolve_cover_mime(
        self,
        *,
        path: Path | None = None,
        url: str | None = None,
        mime_type: str | None = None,
    ) -> str:
        """Resolve a deterministic MIME type for a cover source."""
        normalized = self._normalize_mime_type(mime_type)
        if normalized.startswith("image/"):
            return normalized

        if path is not None:
            guessed, _encoding = mimetypes.guess_type(str(path), strict=False)
            normalized = self._normalize_mime_type(guessed)
            if normalized.startswith("image/"):
                return normalized

        if url:
            guessed, _encoding = mimetypes.guess_type(urlparse(url).path, strict=False)
            normalized = self._normalize_mime_type(guessed)
            if normalized.startswith("image/"):
                return normalized

        return "image/jpeg"

    def build_url_candidate(
        self,
        url: str,
        *,
        mime_type: str | None = None,
        cache_key: str | None = None,
        group_root: str | None = None,
        stage_root: str | None = None,
    ) -> dict[str, str]:
        """Build a deterministic URL-backed cover candidate."""
        resolved_root = self._resolve_root_name(group_root=group_root, stage_root=stage_root)
        normalized_url = str(url).strip()
        resolved_mime = self.resolve_cover_mime(url=normalized_url, mime_type=mime_type)
        resolved_cache_key = str(cache_key or f"url:{_cache_token(normalized_url)}")
        return {
            "kind": "url",
            "candidate_id": f"url:{_cache_token(normalized_url)}",
            "apply_mode": "download",
            "url": normalized_url,
            "mime_type": resolved_mime,
            "cache_key": resolved_cache_key,
            "root_name": resolved_root,
        }

    def discover_cover_candidates(
        self,
        directory: Path,
        *,
        audio_file: Path | None = None,
        group_root: str | None = None,
        stage_root: str | None = None,
    ) -> list[dict[str, str]]:
        """Return canonical cover candidates for a source directory."""
        if not directory.exists() or not directory.is_dir():
            return []

        candidates: list[dict[str, str]] = []
        seen: set[str] = set()
        resolved_root = self._resolve_root_name(group_root=group_root, stage_root=stage_root)

        for name in _FILE_COVER_NAMES:
            candidate = directory / name
            if candidate.exists() and candidate.is_file():
                path_text = str(candidate)
                seen.add(path_text)
                candidates.append(
                    {
                        "kind": "file",
                        "candidate_id": f"file:{candidate.name.lower()}",
                        "apply_mode": "copy",
                        "path": path_text,
                        "mime_type": self.resolve_cover_mime(path=candidate),
                        "cache_key": f"file:{candidate.name.lower()}",
                        "root_name": resolved_root,
                    }
                )

        generic_candidates = sorted(
            candidate
            for candidate in directory.iterdir()
            if candidate.is_file()
            and candidate.suffix.lower() in _GENERIC_COVER_SUFFIXES
            and str(candidate) not in seen
        )
        for candidate in generic_candidates:
            candidates.append(
                {
                    "kind": "file",
                    "candidate_id": f"file:{candidate.name.lower()}",
                    "apply_mode": "copy",
                    "path": str(candidate),
                    "mime_type": self.resolve_cover_mime(path=candidate),
                    "cache_key": f"file:{candidate.name.lower()}",
                    "root_name": resolved_root,
                }
            )

        if audio_file is not None and audio_file.suffix.lower() in _EMBEDDED_SUFFIXES:
            candidates.append(
                {
                    "kind": "embedded",
                    "candidate_id": f"embedded:{audio_file.name}",
                    "apply_mode": "extract_embedded",
                    "path": str(audio_file),
                    "mime_type": "image/jpeg",
                    "cache_key": f"embedded:{audio_file.name.lower()}",
                    "root_name": resolved_root,
                }
            )

        return candidates

    async def apply_cover_candidate(
        self,
        candidate: dict[str, Any],
        *,
        output_dir: Path | None = None,
    ) -> Path | None:
        """Materialize a discovered candidate through its declared apply mode."""
        mode = str(candidate.get("apply_mode") or "")
        source_path = Path(str(candidate.get("path") or ""))

        if not source_path.exists():
            return None

        if mode == "copy":
            if output_dir is None:
                return source_path

            output_dir.mkdir(parents=True, exist_ok=True)
            copied_path = output_dir / source_path.name
            await asyncio.to_thread(shutil.copy2, source_path, copied_path)
            return copied_path

        if mode == "extract_embedded":
            return await self.extract_embedded_cover(source_path)

        if mode == "download":
            url = str(candidate.get("url") or "").strip()
            if not url:
                return None
            mime_type = str(candidate.get("mime_type") or "")
            cache_key = str(candidate.get("cache_key") or "")
            return await self.download_cover(
                url,
                output_dir=output_dir,
                mime_type=mime_type,
                cache_key=cache_key,
            )

        raise CoverError(f"Unsupported apply_mode: {mode}")

    def build_embedded_extract_commands(
        self,
        audio_file: Path,
        output: Path,
    ) -> list[list[str]]:
        """Return deterministic ffmpeg command candidates for embedded extraction."""
        base = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(audio_file),
            "-an",
        ]

        suffix = audio_file.suffix.lower()
        if suffix == ".mp3":
            return [base + ["-c:v", "copy", str(output)]]

        if suffix in {".m4a", ".m4b"}:
            return [
                base + ["-map", "0:v:0", "-c:v", "copy", str(output)],
                base + ["-map", "0:v:0", "-frames:v", "1", str(output)],
            ]

        return [base + ["-frames:v", "1", str(output)]]

    async def extract_embedded_cover(self, audio_file: Path) -> Path | None:
        """Extract embedded cover from audio file."""
        output = audio_file.parent / "cover_extracted.jpg"

        for cmd in self.build_embedded_extract_commands(audio_file, output):
            try:
                if output.exists():
                    output.unlink()

                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()

                if proc.returncode == 0 and output.exists() and output.stat().st_size > 0:
                    return output
            except Exception:
                continue

        if output.exists():
            output.unlink()

        return None

    def find_file_cover(self, directory: Path) -> Path | None:
        """Find the first deterministic file-cover candidate in a directory."""
        for candidate in self.discover_cover_candidates(directory):
            if candidate.get("kind") == "file":
                return Path(str(candidate.get("path") or ""))
        return None

    def _download_output_path(
        self,
        output_dir: Path,
        *,
        url: str,
        mime_type: str | None = None,
        cache_key: str | None = None,
    ) -> Path:
        resolved_mime = self.resolve_cover_mime(url=url, mime_type=mime_type)
        ext = mimetypes.guess_extension(resolved_mime, strict=False) or ""
        if ext == ".jpe":
            ext = ".jpg"
        if not ext:
            parsed = urlparse(url)
            ext = Path(parsed.path).suffix.lower() or ".jpg"
        stem = "cover_downloaded"
        if cache_key:
            stem = f"cover_cache_{_cache_token(str(cache_key))}"
        return output_dir / f"{stem}{ext}"

    async def download_cover(
        self,
        url: str,
        output_dir: Path | None = None,
        *,
        mime_type: str | None = None,
        cache_key: str | None = None,
    ) -> Path | None:
        """Download cover from URL.

        Args:
            url: Cover image URL
            output_dir: Output directory
            mime_type: Optional MIME hint for output extension resolution
            cache_key: Optional deterministic cache key for output naming

        Returns:
            Path to downloaded cover or None
        """
        if not output_dir:
            output_dir = Path("/tmp")

        output_dir.mkdir(parents=True, exist_ok=True)
        output = self._download_output_path(
            output_dir,
            url=url,
            mime_type=mime_type,
            cache_key=cache_key,
        )

        # Use curl for downloading (more reliable than Python requests)
        cmd = [
            "curl",
            "-L",  # Follow redirects
            "-s",  # Silent
            "-o",
            str(output),
            url,
        ]

        try:
            # Check if curl is available
            if not shutil.which("curl"):
                # Fallback to ffmpeg
                cmd = [
                    "ffmpeg",
                    "-hide_banner",
                    "-nostdin",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    url,
                    str(output),
                ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            await proc.communicate()

            if output.exists() and output.stat().st_size > 0:
                return output

        except Exception:
            pass

        if output.exists():
            output.unlink()

        return None

    async def convert_to_jpeg(self, image_path: Path, quality: int = 95) -> Path:
        """Convert image to JPEG format.

        Args:
            image_path: Input image
            quality: JPEG quality (1-100)

        Returns:
            Path to JPEG image
        """
        # Already JPEG?
        if image_path.suffix.lower() in [".jpg", ".jpeg"]:
            return image_path

        output = image_path.with_suffix(".jpg")

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(image_path),
            "-q:v",
            str(100 - quality),  # FFmpeg quality scale is inverted
            str(output),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            await proc.communicate()

            if proc.returncode == 0 and output.exists():
                # Remove original if conversion successful
                if output != image_path:
                    image_path.unlink()
                return output

        except Exception as e:
            raise CoverError(f"Image conversion failed: {e}") from e

        raise CoverError("Image conversion failed")

    async def embed_cover(self, mp3_file: Path, cover_path: Path) -> None:
        """Embed cover into MP3 file.

        Args:
            mp3_file: MP3 file
            cover_path: Cover image path
        """
        temp_file = mp3_file.with_suffix(".covered.mp3")

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(mp3_file),
            "-i",
            str(cover_path),
            "-map",
            "0:a",  # Audio from first input
            "-map",
            "1:v",  # Video (cover) from second input
            "-c:a",
            "copy",  # Copy audio without re-encoding
            "-c:v",
            "copy",  # Copy cover
            "-disposition:v:0",
            "attached_pic",  # Mark as attached picture
            str(temp_file),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                raise CoverError(f"Cover embedding failed: {error_msg}")

            # Replace original with covered version
            temp_file.replace(mp3_file)

        except Exception as e:
            if temp_file.exists():
                temp_file.unlink()
            raise CoverError(f"Failed to embed cover: {e}") from e

    async def embed_covers_batch(self, mp3_files: list[Path], cover_path: Path) -> None:
        """Embed cover into multiple MP3 files.

        Args:
            mp3_files: List of MP3 files
            cover_path: Cover image path
        """
        for mp3_file in mp3_files:
            try:
                await self.embed_cover(mp3_file, cover_path)
            except Exception as e:
                # Log error but continue with other files
                logger.warning(f"Failed to embed cover in {mp3_file.name}: {e}")
