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
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mutagen.id3 import ID3
from mutagen.mp4 import MP4

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


def _ordered_file_candidates(directory: Path) -> list[Path]:
    seen: set[str] = set()
    ordered: list[Path] = []
    for name in _FILE_COVER_NAMES:
        candidate = directory / name
        if candidate.exists() and candidate.is_file():
            ordered.append(candidate)
            seen.add(str(candidate))
    ordered.extend(
        sorted(
            candidate
            for candidate in directory.iterdir()
            if candidate.is_file()
            and candidate.suffix.lower() in _GENERIC_COVER_SUFFIXES
            and str(candidate) not in seen
        )
    )
    return ordered


def _first_audio_source(directory: Path) -> Path | None:
    if not directory.exists() or not directory.is_dir():
        return None
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in _EMBEDDED_SUFFIXES:
            return path
    return None


def _has_embedded_artwork(audio_file: Path) -> bool:
    suffix = audio_file.suffix.lower()
    try:
        if suffix == ".mp3":
            mp3_tags = ID3(str(audio_file))
            apic_frames = mp3_tags.getall("APIC")
            return any(bool(getattr(frame, "data", b"")) for frame in apic_frames)
        if suffix in {".m4a", ".m4b"}:
            mp4_tags: Any = MP4(str(audio_file)).tags
            covers = mp4_tags.get("covr") if mp4_tags is not None else None
            return any(bool(bytes(item)) for item in (covers or []))
    except Exception:
        return False
    return False


def _normalize_relative_path(rel_path: str) -> str:
    value = str(rel_path).replace("\\", "/").strip("/")
    if not value or value == ".":
        return ""
    parts = [part for part in value.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise CoverError("Invalid relative path")
    return "/".join(parts)


def _join_relative_path(base: str, leaf: str) -> str:
    base_norm = _normalize_relative_path(base)
    leaf_norm = _normalize_relative_path(leaf)
    if not base_norm:
        return leaf_norm
    if not leaf_norm:
        return base_norm
    return f"{base_norm}/{leaf_norm}"


def _path_to_relative(*, root_dir: Path, abs_path: Path) -> str:
    return abs_path.resolve().relative_to(root_dir.resolve()).as_posix()


def _file_service_root_dir(file_service: Any, root_name: Any) -> Path:
    getter = getattr(file_service, "_root_dir_path", None)
    if callable(getter):
        return getter(root_name)
    return file_service.root_dir(root_name)


def _file_service_resolve_path(file_service: Any, root_name: Any, rel_path: str) -> Path:
    getter = getattr(file_service, "_resolve_local_path", None)
    if callable(getter):
        return getter(root_name, rel_path)
    return file_service.resolve_abs_path(root_name, rel_path)


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
            candidates = self._discover_cover_candidates_from_paths(
                context.source.parent,
                audio_file=context.source,
            )

            if context.cover_choice == CoverChoice.EMBEDDED:
                candidate = next(
                    (item for item in candidates if item.get("kind") == "embedded"),
                    None,
                )
                if candidate is not None:
                    cover_path = await self._apply_cover_candidate_from_paths(candidate)

            elif context.cover_choice == CoverChoice.FILE:
                candidate = next(
                    (item for item in candidates if item.get("kind") == "file"),
                    None,
                )
                if candidate is not None:
                    file_output_dir = context.stage_dir if context.stage_dir is not None else None
                    cover_path = await self._apply_cover_candidate_from_paths(
                        candidate,
                        output_dir=file_output_dir,
                    )

            elif context.cover_choice == CoverChoice.URL and context.cover_url:
                candidate = self.build_url_candidate(
                    context.cover_url,
                    stage_root="stage" if context.stage_dir is not None else None,
                )
                cover_path = await self._apply_cover_candidate_from_paths(
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

    def discover_cover_candidates_for_ref(
        self,
        *,
        file_service: Any,
        source_root: str,
        source_relative_path: str,
        group_root: str | None = None,
        stage_root: str | None = None,
    ) -> list[dict[str, str]]:
        from plugins.file_io.service import RootName

        root_name = RootName(str(source_root))
        source_rel = _normalize_relative_path(source_relative_path)
        source_dir = _file_service_resolve_path(file_service, root_name, source_rel)
        if source_dir.exists() and source_dir.is_file():
            source_dir = source_dir.parent
            source_rel = _normalize_relative_path(str(Path(source_rel).parent))
        if not source_dir.exists() or not source_dir.is_dir():
            return []

        root_dir = _file_service_root_dir(file_service, root_name)
        candidates = self._discover_cover_candidates_from_paths(
            source_dir,
            audio_file=_first_audio_source(source_dir),
            group_root=group_root,
            stage_root=stage_root,
        )
        out: list[dict[str, str]] = []
        for candidate in candidates:
            entry = {
                "source_root": root_name.value,
                "source_relative_path": source_rel,
                "root_name": str(candidate.get("root_name") or ""),
                "kind": str(candidate.get("kind") or ""),
                "candidate_id": str(candidate.get("candidate_id") or ""),
                "apply_mode": str(candidate.get("apply_mode") or ""),
                "mime_type": str(candidate.get("mime_type") or ""),
                "cache_key": str(candidate.get("cache_key") or ""),
            }
            path_text = str(candidate.get("path") or "")
            if path_text:
                rel_path = _path_to_relative(root_dir=root_dir, abs_path=Path(path_text))
                if str(candidate.get("kind") or "") == "embedded":
                    entry["audio_relative_path"] = rel_path
                else:
                    entry["candidate_relative_path"] = rel_path
            url = str(candidate.get("url") or "")
            if url:
                entry["url"] = url
            out.append(entry)
        return out

    async def apply_cover_candidate_for_ref(
        self,
        *,
        file_service: Any,
        candidate: dict[str, Any],
        output_root: str,
        output_relative_dir: str,
    ) -> dict[str, str] | None:
        from plugins.file_io.service import RootName

        output_root_name = RootName(str(output_root))
        output_rel_dir = _normalize_relative_path(output_relative_dir)
        output_dir = _file_service_resolve_path(file_service, output_root_name, output_rel_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        source_root_text = str(candidate.get("source_root") or "")
        source_root = RootName(source_root_text) if source_root_text else None
        mode = str(candidate.get("apply_mode") or "")

        if mode == "copy" and source_root is not None:
            rel = _normalize_relative_path(str(candidate.get("candidate_relative_path") or ""))
            if not rel:
                return None
            source_path = _file_service_resolve_path(file_service, source_root, rel)
            materialized = await self._apply_cover_candidate_from_paths(
                {
                    "kind": str(candidate.get("kind") or "file"),
                    "candidate_id": str(candidate.get("candidate_id") or ""),
                    "apply_mode": "copy",
                    "path": str(source_path),
                    "mime_type": str(candidate.get("mime_type") or ""),
                    "cache_key": str(candidate.get("cache_key") or ""),
                    "root_name": str(candidate.get("root_name") or ""),
                },
                output_dir=output_dir,
            )
        elif mode == "extract_embedded" and source_root is not None:
            rel = _normalize_relative_path(str(candidate.get("audio_relative_path") or ""))
            if not rel:
                return None
            audio_file = _file_service_resolve_path(file_service, source_root, rel)
            materialized = await self.extract_embedded_cover(
                audio_file,
                output_path=output_dir / "cover_extracted.jpg",
            )
        elif mode == "download":
            materialized = await self.download_cover(
                str(candidate.get("url") or "").strip(),
                output_dir=output_dir,
                mime_type=str(candidate.get("mime_type") or ""),
                cache_key=str(candidate.get("cache_key") or ""),
            )
        else:
            raise CoverError(f"Unsupported apply_mode: {mode}")

        if materialized is None:
            return None
        return {
            "root": output_root_name.value,
            "relative_path": _join_relative_path(output_rel_dir, materialized.name),
        }

    def _discover_cover_candidates_from_paths(
        self,
        directory: Path,
        *,
        audio_file: Path | None = None,
        group_root: str | None = None,
        stage_root: str | None = None,
    ) -> list[dict[str, str]]:
        if not directory.exists() or not directory.is_dir():
            return []

        candidates: list[dict[str, str]] = []
        resolved_root = self._resolve_root_name(group_root=group_root, stage_root=stage_root)
        scopes = [("primary", directory)]
        fallback = directory.parent
        if fallback.exists() and fallback.is_dir() and fallback != directory:
            scopes.append(("fallback", fallback))

        ordered_files = [
            (scope_name, candidate)
            for scope_name, scope_dir in scopes
            for candidate in _ordered_file_candidates(scope_dir)
        ]
        duplicate_names = {
            name
            for name, count in Counter(path.name.lower() for _, path in ordered_files).items()
            if count > 1
        }
        base_keys: list[str] = []
        for scope_name, candidate in ordered_files:
            name_key = candidate.name.lower()
            suffix = "@fallback" if scope_name == "fallback" and name_key in duplicate_names else ""
            base_keys.append(f"file:{name_key}{suffix}")

        duplicate_base_keys = {key for key, count in Counter(base_keys).items() if count > 1}
        seen_base_keys: Counter[str] = Counter()
        for (_scope_name, candidate), base_key in zip(ordered_files, base_keys, strict=True):
            seen_base_keys[base_key] += 1
            ordinal_suffix = ""
            if base_key in duplicate_base_keys and seen_base_keys[base_key] > 1:
                ordinal_suffix = f"#{seen_base_keys[base_key]}"
            candidate_key = f"{base_key}{ordinal_suffix}"
            candidates.append(
                {
                    "kind": "file",
                    "candidate_id": candidate_key,
                    "apply_mode": "copy",
                    "path": str(candidate),
                    "mime_type": self.resolve_cover_mime(path=candidate),
                    "cache_key": candidate_key,
                    "root_name": resolved_root,
                }
            )

        if (
            audio_file is not None
            and audio_file.suffix.lower() in _EMBEDDED_SUFFIXES
            and _has_embedded_artwork(audio_file)
        ):
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

    async def _apply_cover_candidate_from_paths(
        self,
        candidate: dict[str, Any],
        *,
        output_dir: Path | None = None,
    ) -> Path | None:
        mode = str(candidate.get("apply_mode") or "")

        if mode == "copy":
            source_path = Path(str(candidate.get("path") or ""))
            if not source_path.exists():
                return None
            if output_dir is None:
                return source_path
            output_dir.mkdir(parents=True, exist_ok=True)
            copied_path = output_dir / source_path.name
            await asyncio.to_thread(shutil.copy2, source_path, copied_path)
            return copied_path

        if mode == "extract_embedded":
            source_path = Path(str(candidate.get("path") or ""))
            if not source_path.exists():
                return None
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

    async def extract_embedded_cover(
        self,
        audio_file: Path,
        *,
        output_path: Path | None = None,
    ) -> Path | None:
        """Extract embedded cover from audio file."""
        output = output_path or (audio_file.parent / "cover_extracted.jpg")

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
        for candidate in self._discover_cover_candidates_from_paths(directory):
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
        if output_dir is None:
            return None

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
