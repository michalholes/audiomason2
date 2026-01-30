"""Detection utilities for preflight phase.

These helpers detect what's available in files and suggest good defaults.
Core provides these utilities, but UI plugins decide how to use them.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any


def guess_author_from_path(path: Path) -> str | None:
    """Try to extract author from file/directory name.

    Common patterns:
    - "Orwell, George - 1984.m4a"
    - "George Orwell - 1984.m4a"
    - "/books/George Orwell/1984.m4a"

    Args:
        path: File path

    Returns:
        Guessed author or None
    """
    # Try filename patterns
    filename = path.stem

    # Pattern: "Author - Title"
    if " - " in filename:
        parts = filename.split(" - ", 1)
        author = parts[0].strip()
        if author and len(author) > 2:
            return author

    # Pattern: "Lastname, Firstname - Title"
    match = re.match(r"^([A-Z][a-z]+,\s*[A-Z][a-z]+)\s*-", filename)
    if match:
        return match.group(1)

    # Try parent directory name
    parent = path.parent.name
    if parent and parent.lower() not in {"audiobooks", "books", "downloads", "tmp"}:
        return parent

    return None


def guess_title_from_path(path: Path) -> str | None:
    """Try to extract title from filename.

    Args:
        path: File path

    Returns:
        Guessed title or None
    """
    filename = path.stem

    # Remove common prefixes
    filename = re.sub(r"^\d+[-_\s]*", "", filename)  # Remove leading numbers

    # Pattern: "Author - Title"
    if " - " in filename:
        parts = filename.split(" - ", 1)
        if len(parts) > 1:
            title = parts[1].strip()
            if title:
                return title

    # Pattern: "Title (Year)"
    match = re.match(r"^(.+?)\s*\(\d{4}\)", filename)
    if match:
        return match.group(1).strip()

    # Just use filename
    return filename if filename else None


def detect_file_groups(files: list[Path]) -> dict[str, list[Path]]:
    """Group files by detected author.

    This is used for smart question grouping - ask author once for multiple files.

    Args:
        files: List of file paths

    Returns:
        Dict of author -> list of files
    """
    groups: dict[str, list[Path]] = defaultdict(list)

    for file in files:
        author = guess_author_from_path(file)
        key = author if author else "unknown"
        groups[key].append(file)

    return dict(groups)


def extract_existing_metadata(path: Path) -> dict[str, Any]:
    """Read any existing metadata from file.

    This would use mutagen or similar to read ID3/M4A tags.
    For now, placeholder.

    Args:
        path: File path

    Returns:
        Dict of metadata
    """
    # TODO: Implement with mutagen
    # For now, return empty
    return {}


def has_embedded_cover(path: Path) -> bool:
    """Check if file has embedded cover art.

    Args:
        path: File path

    Returns:
        True if has embedded cover
    """
    # TODO: Implement with mutagen
    return False


def find_file_cover(directory: Path) -> Path | None:
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
    ]

    for name in cover_names:
        candidate = directory / name
        if candidate.exists() and candidate.is_file():
            return candidate

    return None


def detect_chapters(path: Path) -> tuple[bool, int]:
    """Detect if file has chapters.

    Args:
        path: File path

    Returns:
        (has_chapters, chapter_count) tuple
    """
    # TODO: Implement with ffprobe
    return False, 0


def detect_format(path: Path) -> str:
    """Detect audio format from file.

    Args:
        path: File path

    Returns:
        Format string (mp3, m4a, opus, etc.)
    """
    suffix = path.suffix.lower()

    format_map = {
        ".mp3": "mp3",
        ".m4a": "m4a",
        ".m4b": "m4a",
        ".opus": "opus",
        ".ogg": "ogg",
        ".flac": "flac",
        ".wav": "wav",
    }

    return format_map.get(suffix, "unknown")


def guess_year_from_path(path: Path) -> int | None:
    """Try to extract year from filename or path.

    Pattern: "Title (2024)"

    Args:
        path: File path

    Returns:
        Guessed year or None
    """
    filename = path.stem

    # Pattern: (YYYY)
    match = re.search(r"\((\d{4})\)", filename)
    if match:
        year = int(match.group(1))
        if 1900 <= year <= 2100:
            return year

    # Pattern: [YYYY]
    match = re.search(r"\[(\d{4})\]", filename)
    if match:
        year = int(match.group(1))
        if 1900 <= year <= 2100:
            return year

    return None
