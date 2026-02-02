"""Processing context that flows through the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class State(Enum):
    """Processing state."""

    INIT = "init"
    PREFLIGHT = "preflight"
    COLLECTING_INPUT = "collecting_input"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"
    INTERRUPTED = "interrupted"


class CoverChoice(Enum):
    """Cover source choice."""

    EMBEDDED = "embedded"
    FILE = "file"
    URL = "url"
    SKIP = "skip"


@dataclass
class PreflightResult:
    """Results from preflight detection phase.

    This contains everything detected BEFORE asking user.
    Used to make intelligent questions with good defaults.
    """

    # Existing metadata
    has_title: bool = False
    has_author: bool = False
    has_year: bool = False
    existing_metadata: dict[str, Any] = field(default_factory=dict)

    # Cover detection
    has_embedded_cover: bool = False
    has_file_cover: bool = False
    file_cover_path: Path | None = None

    # Format detection
    is_m4a: bool = False
    is_opus: bool = False
    is_mp3: bool = False

    # Chapter detection
    has_chapters: bool = False
    chapter_count: int = 0

    # Guessed values (for defaults)
    guessed_author: str | None = None
    guessed_title: str | None = None
    guessed_year: int | None = None

    # File info
    file_size_bytes: int = 0
    duration_seconds: float | None = None


@dataclass
class ProcessingContext:
    """Context that flows through the entire pipeline.

    This contains:
    1. Input file info
    2. ALL user decisions (from PHASE 1)
    3. Preflight detection results
    4. Processing state (from PHASE 2)
    5. Output results
    6. Profiling data
    7. Errors
    """

    # ═══════════════════════════════════════════
    #  IDENTIFICATION
    # ═══════════════════════════════════════════

    id: str  # Unique context ID
    source: Path  # Input file path

    # ═══════════════════════════════════════════
    #  USER DECISIONS (ALL from PHASE 1)
    # ═══════════════════════════════════════════

    # Required metadata
    author: str | None = None
    title: str | None = None
    year: int | None = None

    # Optional metadata
    narrator: str | None = None
    series: str | None = None
    series_number: int | None = None
    genre: str | None = None
    language: str | None = None
    isbn: str | None = None

    # Cover decisions
    cover_choice: CoverChoice = CoverChoice.SKIP
    cover_url: str | None = None  # If cover_choice == URL

    # Processing options
    split_chapters: bool = False
    loudnorm: bool = False
    target_bitrate: str = "128k"

    # ═══════════════════════════════════════════
    #  PREFLIGHT RESULTS
    # ═══════════════════════════════════════════

    preflight: PreflightResult | None = None

    # ═══════════════════════════════════════════
    #  PROCESSING STATE (PHASE 2)
    # ═══════════════════════════════════════════

    state: State = State.INIT
    current_step: str | None = None
    progress: float = 0.0  # 0.0 - 1.0
    completed_steps: list[str] = field(default_factory=list)

    # ═══════════════════════════════════════════
    #  WORKING PATHS
    # ═══════════════════════════════════════════

    stage_dir: Path | None = None  # Temporary working directory
    output_path: Path | None = None  # Final output location

    # ═══════════════════════════════════════════
    #  RESULTS
    # ═══════════════════════════════════════════

    # Generated files
    converted_files: list[Path] = field(default_factory=list)
    cover_path: Path | None = None

    # Metadata
    final_metadata: dict[str, Any] = field(default_factory=dict)

    # ═══════════════════════════════════════════
    #  PROFILING
    # ═══════════════════════════════════════════

    timings: dict[str, float] = field(default_factory=dict)  # step_name -> seconds
    start_time: float | None = None
    end_time: float | None = None

    # ═══════════════════════════════════════════
    #  ERROR HANDLING
    # ═══════════════════════════════════════════

    errors: list[Exception] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # ═══════════════════════════════════════════
    #  PERSISTENCE (for resume)
    # ═══════════════════════════════════════════

    checkpoint_path: Path | None = None
    can_resume: bool = True

    def add_timing(self, step: str, duration: float) -> None:
        """Add timing for a step."""
        self.timings[step] = duration

    def add_error(self, error: Exception) -> None:
        """Add error."""
        self.errors.append(error)

    def add_warning(self, warning: str) -> None:
        """Add warning."""
        self.warnings.append(warning)

    def mark_step_complete(self, step: str) -> None:
        """Mark step as completed."""
        if step not in self.completed_steps:
            self.completed_steps.append(step)

    @property
    def has_errors(self) -> bool:
        """Check if context has errors."""
        return len(self.errors) > 0

    @property
    def total_time(self) -> float | None:
        """Total processing time in seconds."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

    publisher: str | None = None
    description: str | None = None

    output_dir: Path | None = None  # Final output directory
