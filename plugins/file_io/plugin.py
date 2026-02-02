"""File I/O plugin - import and export operations."""

from __future__ import annotations

import shutil
from pathlib import Path

from audiomason.core import ProcessingContext
from audiomason.core.context import PreflightResult
from audiomason.core.detection import (
    detect_format,
    find_file_cover,
    guess_author_from_path,
    guess_title_from_path,
    guess_year_from_path,
)
from audiomason.core.errors import FileError


class FileIOPlugin:
    """File I/O plugin.

    Handles:
    - Import: Copy source to staging area
    - Export: Move processed files to output directory
    - Preflight: Detect metadata from filenames
    - Extract: Extract archives
    """

    def __init__(self, config: dict | None = None) -> None:
        """Initialize plugin.

        Args:
            config: Plugin configuration
        """
        self.config = config or {}
        self.stage_dir = Path(self.config.get("stage_dir", "/tmp/audiomason/stage"))
        self.output_dir = Path(self.config.get("output_dir", "~/Audiobooks/output"))

    async def import_file(self, context: ProcessingContext) -> ProcessingContext:
        """Import source file to staging area.

        Args:
            context: Processing context

        Returns:
            Updated context with stage_dir set
        """
        source = context.source

        if not source.exists():
            raise FileError(f"Source file not found: {source}")

        # Create unique staging directory for this book
        import uuid

        stage_dir = self.stage_dir / f"book_{uuid.uuid4().hex[:8]}"
        stage_dir.mkdir(parents=True, exist_ok=True)

        # Copy source to stage
        staged_file = stage_dir / source.name
        shutil.copy2(source, staged_file)

        # Update context
        context.stage_dir = stage_dir
        context.add_warning(f"Imported to: {stage_dir}")

        return context

    async def export_files(self, context: ProcessingContext) -> ProcessingContext:
        """Export processed files to output directory.

        Args:
            context: Processing context

        Returns:
            Updated context with output_path set
        """
        if not context.converted_files:
            raise FileError("No files to export")

        # Create output directory
        # Format: Author - Title/
        author = context.author or "Unknown"
        title = context.title or "Untitled"

        # Clean names for filesystem
        author_clean = self._sanitize_filename(author)
        title_clean = self._sanitize_filename(title)

        output_dir = self.output_dir.expanduser() / f"{author_clean} - {title_clean}"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Move files
        exported = []
        for file in context.converted_files:
            if file.exists():
                dest = output_dir / file.name
                shutil.move(str(file), str(dest))
                exported.append(dest)

        context.output_path = output_dir
        context.add_warning(f"Exported {len(exported)} file(s) to: {output_dir}")

        # Cleanup stage directory
        if context.stage_dir and context.stage_dir.exists():
            shutil.rmtree(context.stage_dir, ignore_errors=True)

        return context

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize string for use in filename.

        Args:
            name: Original name

        Returns:
            Sanitized name
        """
        # Remove or replace problematic characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, "_")

        # Remove leading/trailing spaces and dots
        name = name.strip(". ")

        # Limit length
        if len(name) > 100:
            name = name[:100]

        return name if name else "Unnamed"

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        """Process context - can be used for either import or export.

        This is a bit of a hack - normally we'd have separate plugins.
        For MVP, we're combining them.

        Args:
            context: Processing context

        Returns:
            Updated context
        """
        # If stage_dir not set, assume import phase
        if context.stage_dir is None:
            return await self.import_file(context)

        # If converted_files present, assume export phase
        if context.converted_files:
            return await self.export_files(context)

        return context

    async def preflight(self, context: ProcessingContext) -> ProcessingContext:
        """Run preflight detection on source files.

        Detects metadata from filenames and paths, checks for covers,
        and populates preflight results in context.

        Args:
            context: Processing context

        Returns:
            Updated context with preflight results
        """
        source = context.source

        if not source.exists():
            raise FileError(f"Source not found: {source}")

        result = PreflightResult()

        # Detect format
        fmt = detect_format(source)
        result.is_m4a = fmt == "m4a"
        result.is_opus = fmt == "opus"
        result.is_mp3 = fmt == "mp3"

        # Guess metadata from path
        result.guessed_author = guess_author_from_path(source)
        result.guessed_title = guess_title_from_path(source)
        result.guessed_year = guess_year_from_path(source)

        # Check for cover file
        parent_dir = source.parent if source.is_file() else source
        cover = find_file_cover(parent_dir)
        result.has_file_cover = cover is not None
        result.file_cover_path = cover

        # Store in context
        context.preflight = result

        return context

    async def extract_archive(self, context: ProcessingContext) -> ProcessingContext:
        """Extract archive file to staging area.

        Supports ZIP, RAR, 7Z formats.

        Args:
            context: Processing context

        Returns:
            Updated context with extracted files
        """
        import zipfile

        source = context.source

        if not source.exists():
            raise FileError(f"Archive not found: {source}")

        # Create extraction directory
        extract_dir = self.stage_dir / f"extract_{source.stem}"
        extract_dir.mkdir(parents=True, exist_ok=True)

        # Extract based on type
        suffix = source.suffix.lower()

        if suffix == ".zip":
            with zipfile.ZipFile(source, "r") as zip_ref:
                zip_ref.extractall(extract_dir)
        elif suffix == ".rar":
            try:
                import rarfile  # type: ignore[import-not-found]

                with rarfile.RarFile(source, "r") as rar_ref:
                    rar_ref.extractall(extract_dir)
            except ImportError:
                raise FileError(
                    "RAR support not available. Install with: pip install rarfile"
                ) from None
        elif suffix == ".7z":
            try:
                import py7zr  # type: ignore[import-not-found]

                with py7zr.SevenZipFile(source, "r") as sz_ref:
                    sz_ref.extractall(extract_dir)
            except ImportError:
                raise FileError(
                    "7Z support not available. Install with: pip install py7zr"
                ) from None
        else:
            raise FileError(f"Unsupported archive format: {suffix}")

        context.stage_dir = extract_dir
        context.add_warning(f"Extracted to: {extract_dir}")

        return context

    async def organize(
        self,
        context: ProcessingContext,
        structure: str = "flat",
        filename_format: str = "original",
    ) -> ProcessingContext:
        """Organize output files according to structure and naming convention.

        Args:
            context: Processing context
            structure: Directory structure ("flat", "by_author", "by_genre")
            filename_format: Filename format ("original", "01.mp3", "chapter_01.mp3")

        Returns:
            Updated context
        """
        # TODO: Implement full organization logic
        # For now, this is a placeholder that does nothing
        #
        # Planned features:
        # - structure == "flat": All files in one directory
        # - structure == "by_author": Author/Title/files
        # - structure == "by_genre": Genre/Author/Title/files
        #
        # - filename_format == "original": Keep original names
        # - filename_format == "01.mp3": Sequential numbering
        # - filename_format == "chapter_01.mp3": "chapter_" prefix + number

        context.add_warning("organize() called but not yet fully implemented")
        return context
