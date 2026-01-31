"""Synchronous File I/O Plugin - detect, import, export operations."""

from __future__ import annotations

import shutil
import zipfile
import tarfile
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from audiomason.core import ProcessingContext
from audiomason.core.errors import FileError


@dataclass
class SourceInfo:
    """Information about detected source."""
    path: Path
    type: str  # 'directory' | 'archive' | 'audio_file'
    name: str
    has_audio: bool = False
    has_cover: bool = False


class FileIOSync:
    """Synchronous file I/O operations.
    
    Handles:
    - Source detection in inbox
    - Import to staging area
    - Export to output directory
    - Archive extraction
    """

    ARCHIVE_EXTS = {'.zip', '.rar', '.7z', '.tar', '.tar.gz', '.tgz'}
    AUDIO_EXTS = {'.mp3', '.m4a', '.m4b', '.opus', '.ogg', '.flac', '.wav'}
    IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}

    def __init__(self, config: dict | None = None) -> None:
        """Initialize plugin.
        
        Args:
            config: Plugin configuration
        """
        self.config = config or {}
        self.verbosity = self.config.get('verbosity', 1)
        
        # Paths from config
        inbox = self.config.get('inbox_dir', '~/Audiobooks/inbox')
        stage = self.config.get('stage_dir', '/tmp/audiomason/stage')
        output = self.config.get('output_dir', '~/Audiobooks/output')
        
        self.inbox_dir = Path(inbox).expanduser().resolve()
        self.stage_dir = Path(stage).expanduser().resolve()
        self.output_dir = Path(output).expanduser().resolve()

    def _log_debug(self, msg: str) -> None:
        """Log debug message (verbosity >= 3)."""
        if self.verbosity >= 3:
            print(f"[DEBUG] [file_io_sync] {msg}")

    def _log_verbose(self, msg: str) -> None:
        """Log verbose message (verbosity >= 2)."""
        if self.verbosity >= 2:
            print(f"[VERBOSE] [file_io_sync] {msg}")

    def _log_info(self, msg: str) -> None:
        """Log info message (verbosity >= 1)."""
        if self.verbosity >= 1:
            print(f"[file_io_sync] {msg}")

    def _log_error(self, msg: str) -> None:
        """Log error message (always shown)."""
        print(f"[ERROR] [file_io_sync] {msg}")

    def detect_sources(self, inbox_path: Optional[Path] = None) -> list[SourceInfo]:
        """Detect all sources in inbox directory.
        
        Args:
            inbox_path: Override inbox directory (optional)
            
        Returns:
            List of detected sources
        """
        search_dir = inbox_path or self.inbox_dir
        
        if not search_dir.exists():
            self._log_error(f"Inbox directory not found: {search_dir}")
            return []
        
        self._log_debug(f"Scanning inbox: {search_dir}")
        
        sources = []
        
        for item in sorted(search_dir.iterdir()):
            # Skip hidden files and AM internal files
            if item.name.startswith('.') or item.name.startswith('_'):
                continue
            
            if item.name in {'import.log.jsonl', '.DS_Store'}:
                continue
            
            # Check if directory with audio
            if item.is_dir():
                has_audio = self._has_audio_files(item)
                has_cover = self._has_cover_files(item)
                
                if has_audio:
                    sources.append(SourceInfo(
                        path=item,
                        type='directory',
                        name=item.name,
                        has_audio=True,
                        has_cover=has_cover
                    ))
                    self._log_debug(f"Found directory: {item.name} (audio={has_audio}, cover={has_cover})")
            
            # Check if archive
            elif item.is_file() and item.suffix.lower() in self.ARCHIVE_EXTS:
                sources.append(SourceInfo(
                    path=item,
                    type='archive',
                    name=item.name,
                    has_audio=True  # Assume archives contain audio
                ))
                self._log_debug(f"Found archive: {item.name}")
            
            # Check if standalone audio file
            elif item.is_file() and item.suffix.lower() in self.AUDIO_EXTS:
                sources.append(SourceInfo(
                    path=item,
                    type='audio_file',
                    name=item.name,
                    has_audio=True
                ))
                self._log_debug(f"Found audio file: {item.name}")
        
        self._log_info(f"Found {len(sources)} source(s) in inbox")
        return sources

    def _has_audio_files(self, directory: Path) -> bool:
        """Check if directory contains audio files.
        
        Args:
            directory: Directory to check
            
        Returns:
            True if audio files found
        """
        for item in directory.rglob('*'):
            if item.is_file() and item.suffix.lower() in self.AUDIO_EXTS:
                return True
        return False

    def _has_cover_files(self, directory: Path) -> bool:
        """Check if directory contains image files.
        
        Args:
            directory: Directory to check
            
        Returns:
            True if image files found
        """
        for item in directory.iterdir():
            if item.is_file() and item.suffix.lower() in self.IMAGE_EXTS:
                return True
        return False

    def import_to_stage(self, context: ProcessingContext) -> ProcessingContext:
        """Import source to staging area.
        
        Args:
            context: Processing context (source taken from context.source)
            
        Returns:
            Updated processing context
            
        Raises:
            FileError: If import fails
        """
        # Get source from context
        if not hasattr(context, 'source') or not context.source:
            raise FileError("No source in context")
        
        source = context.source
        
        if not source.exists():
            raise FileError(f"Source not found: {source}")
        
        # Create unique stage directory
        stage_name = self._sanitize_filename(source.stem)
        stage_path = self.stage_dir / stage_name
        
        self._log_info(f"Importing to stage: {source.name} -> {stage_path.name}")
        
        # Clean stage directory if exists
        if stage_path.exists():
            self._log_debug(f"Cleaning existing stage: {stage_path}")
            shutil.rmtree(stage_path)
        
        stage_path.mkdir(parents=True, exist_ok=True)
        
        # Import based on source type
        if source.is_dir():
            self._copy_directory(source, stage_path)
        elif source.suffix.lower() in self.ARCHIVE_EXTS:
            self._extract_archive(source, stage_path)
        elif source.suffix.lower() in self.AUDIO_EXTS:
            # Single audio file - copy to stage
            shutil.copy2(source, stage_path / source.name)
        else:
            raise FileError(f"Unsupported source type: {source}")
        
        # Update context
        context.stage_dir = stage_path
        
        self._log_verbose(f"Import complete: {stage_path}")
        return context

    def _copy_directory(self, src: Path, dst: Path) -> None:
        """Recursively copy directory contents.
        
        Args:
            src: Source directory
            dst: Destination directory
        """
        self._log_debug(f"Copying directory: {src} -> {dst}")
        
        for item in src.rglob('*'):
            if item.is_file():
                rel_path = item.relative_to(src)
                dest_file = dst / rel_path
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest_file)

    def _extract_archive(self, archive: Path, destination: Path) -> None:
        """Extract archive to destination.
        
        Args:
            archive: Archive file path
            destination: Destination directory
            
        Raises:
            FileError: If extraction fails
        """
        self._log_debug(f"Extracting archive: {archive} -> {destination}")
        
        try:
            if archive.suffix.lower() == '.zip':
                with zipfile.ZipFile(archive, 'r') as zf:
                    zf.extractall(destination)
            elif archive.suffix.lower() in {'.tar', '.tar.gz', '.tgz'}:
                with tarfile.open(archive, 'r:*') as tf:
                    tf.extractall(destination)
            else:
                raise FileError(f"Unsupported archive format: {archive.suffix}")
        except Exception as e:
            raise FileError(f"Archive extraction failed: {e}") from e

    def export_to_output(self, context: ProcessingContext) -> Path:
        """Export processed files to output directory.
        
        Args:
            context: Processing context
            
        Returns:
            Path to output directory
            
        Raises:
            FileError: If export fails
        """
        if not hasattr(context, 'converted_files') or not context.converted_files:
            raise FileError("No converted files to export")
        
        # Create output directory: Author - Title/
        author = getattr(context, 'author', 'Unknown Author')
        title = getattr(context, 'title', 'Unknown Title')
        
        author_clean = self._sanitize_filename(author)
        title_clean = self._sanitize_filename(title)
        
        output_path = self.output_dir / f"{author_clean} - {title_clean}"
        
        self._log_info(f"Exporting to: {output_path}")
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Move converted files
        exported_files = []
        for src_file in context.converted_files:
            if not src_file.exists():
                self._log_error(f"File not found: {src_file}")
                continue
            
            dest_file = output_path / src_file.name
            
            # Handle duplicate filenames
            if dest_file.exists():
                base = dest_file.stem
                ext = dest_file.suffix
                counter = 1
                while dest_file.exists():
                    dest_file = output_path / f"{base}_{counter}{ext}"
                    counter += 1
            
            self._log_debug(f"Moving: {src_file.name} -> {dest_file.name}")
            shutil.move(str(src_file), str(dest_file))
            exported_files.append(dest_file)
        
        # Copy cover if exists
        if hasattr(context, 'cover_path') and context.cover_path:
            if context.cover_path.exists():
                cover_dest = output_path / 'cover.jpg'
                shutil.copy2(context.cover_path, cover_dest)
                self._log_debug(f"Copied cover: {cover_dest}")
        
        context.output_path = output_path
        context.exported_files = exported_files
        
        self._log_info(f"Exported {len(exported_files)} file(s)")
        return output_path

    def cleanup_stage(self, context: ProcessingContext) -> None:
        """Clean up staging directory.
        
        Args:
            context: Processing context
        """
        if not hasattr(context, 'stage_dir') or not context.stage_dir:
            return
        
        stage_dir = context.stage_dir
        
        if stage_dir.exists():
            self._log_info(f"Cleaning stage: {stage_dir}")
            shutil.rmtree(stage_dir)

    def cleanup_inbox(self, context: ProcessingContext) -> None:
        """Clean up source from inbox.
        
        Args:
            context: Processing context
        """
        if not hasattr(context, 'source') or not context.source:
            return
        
        source = context.source
        
        if source.exists():
            self._log_info(f"Cleaning inbox: {source}")
            if source.is_dir():
                shutil.rmtree(source)
            else:
                source.unlink()

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Sanitize filename for filesystem.
        
        Args:
            name: Original name
            
        Returns:
            Sanitized name
        """
        # Remove/replace problematic characters
        replacements = {
            '/': '-',
            '\\': '-',
            ':': '-',
            '*': '',
            '?': '',
            '"': '',
            '<': '',
            '>': '',
            '|': '',
        }
        
        result = name
        for old, new in replacements.items():
            result = result.replace(old, new)
        
        # Remove multiple spaces and leading/trailing spaces
        result = ' '.join(result.split())
        
        return result.strip()

    def process(self, context: ProcessingContext) -> ProcessingContext:
        """Main processing method (IProcessor interface).
        
        This is a pass-through - actual methods are called directly by wizard.
        
        Args:
            context: Processing context
            
        Returns:
            Updated context
        """
        return context
