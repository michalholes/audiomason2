"""File I/O plugin - import and export operations."""

from __future__ import annotations

import shutil
from pathlib import Path

from audiomason.core import ProcessingContext
from audiomason.core.errors import FileError


class FileIOPlugin:
    """File I/O plugin.

    Handles:
    - Import: Copy source to staging area
    - Export: Move processed files to output directory
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
