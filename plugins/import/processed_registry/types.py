"""Processed registry models.

ASCII-only.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessedRegistryStats:
    count: int
