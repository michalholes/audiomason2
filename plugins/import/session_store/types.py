"""Import run state models.

ASCII-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

SourceHandlingMode = Literal["stage", "inplace", "hybrid"]


@dataclass(frozen=True)
class ProcessedRegistryPolicy:
    """Policy placeholder for processed registry behavior."""

    enabled: bool = True
    scope: str = "book_folder"


@dataclass(frozen=True)
class PreflightCacheMetadata:
    """Metadata about the preflight cache (placeholder)."""

    cache_key: str | None = None
    cache_hit: bool = False


@dataclass(frozen=True)
class ImportRunState:
    """Wizard-run scoped import runtime state.

    This is a run-scoped artifact keyed by wizard job id (run id).
    It contains only configuration/state. It does not perform any work.
    """

    # Required fields (Issue 402)
    source_selection_snapshot: dict[str, Any]
    source_handling_mode: SourceHandlingMode = "stage"
    parallelism_n: int = 1
    global_options: dict[str, Any] | None = None

    # Placeholders (Issue 402)
    conflict_policy: dict[str, Any] | None = None
    filename_normalization_policy: dict[str, Any] | None = None
    defaults_memory: dict[str, Any] | None = None
    processed_registry_policy: ProcessedRegistryPolicy = ProcessedRegistryPolicy()
    public_db_lookup: dict[str, Any] | None = None
    preflight_cache: PreflightCacheMetadata = PreflightCacheMetadata()
