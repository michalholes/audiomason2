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
import shutil
from pathlib import Path
from urllib.parse import urlparse

from audiomason.core import ProcessingContext, CoverChoice
from audiomason.core.errors import CoverError


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
            if context.cover_choice == CoverChoice.EMBEDDED:
                cover_path = await self.extract_embedded_cover(context.source)

            elif context.cover_choice == CoverChoice.FILE:
                cover_path = self.find_file_cover(context.source.parent)

            elif context.cover_choice == CoverChoice.URL:
                if context.cover_url:
                    cover_path = await self.download_cover(context.cover_url, context.stage_dir)

            if cover_path and cover_path.exists():
                # Convert to JPEG if needed
                cover_path = await self.convert_to_jpeg(cover_path)
                context.cover_path = cover_path
                context.add_warning(f"Cover: {cover_path.name}")
            else:
                context.add_warning("Cover not found")

        except Exception as e:
            context.add_warning(f"Cover error: {e}")

        return context

    async def extract_embedded_cover(self, audio_file: Path) -> Path | None:
        """Extract embedded cover from audio file.

        Args:
            audio_file: Audio file (MP3 or M4A)

        Returns:
            Path to extracted cover or None
        """
        output = audio_file.parent / "cover_extracted.jpg"

        # Try MP3 first
        if audio_file.suffix.lower() == ".mp3":
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-nostdin",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(audio_file),
                "-an",  # No audio
                "-c:v",
                "copy",
                str(output),
            ]
        else:
            # M4A and others
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-nostdin",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(audio_file),
                "-an",
                str(output),
            ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            await proc.communicate()

            if proc.returncode == 0 and output.exists() and output.stat().st_size > 0:
                return output

        except Exception:
            pass

        if output.exists():
            output.unlink()

        return None

    def find_file_cover(self, directory: Path) -> Path | None:
        """Find cover file in directory.

        Looks for: cover.jpg, cover.png, folder.jpg, etc.

        Args:
            directory: Directory to search

        Returns:
            Cover file path or None
        """
        if not directory.exists() or not directory.is_dir():
            return None

        cover_names = [
            "cover.jpg",
            "cover.jpeg",
            "cover.png",
            "cover.webp",
            "folder.jpg",
            "folder.jpeg",
            "folder.png",
            "front.jpg",
            "front.png",
        ]

        for name in cover_names:
            candidate = directory / name
            if candidate.exists() and candidate.is_file():
                return candidate

        # Try any jpg/png in directory
        for ext in [".jpg", ".jpeg", ".png"]:
            candidates = list(directory.glob(f"*{ext}"))
            if candidates:
                return candidates[0]

        return None

    async def download_cover(self, url: str, output_dir: Path | None = None) -> Path | None:
        """Download cover from URL.

        Args:
            url: Cover image URL
            output_dir: Output directory

        Returns:
            Path to downloaded cover or None
        """
        if not output_dir:
            output_dir = Path("/tmp")

        output_dir.mkdir(parents=True, exist_ok=True)

        # Determine extension from URL
        parsed = urlparse(url)
        ext = Path(parsed.path).suffix
        if not ext:
            ext = ".jpg"

        output = output_dir / f"cover_downloaded{ext}"

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
                print(f"Failed to embed cover in {mp3_file.name}: {e}")
