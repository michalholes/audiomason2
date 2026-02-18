"""Shared serialization helpers for import plugin.

This module provides canonical JSON serialization for deterministic outputs.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from .fingerprints import canonical_json_bytes


def canonical_serialize(obj: Any) -> bytes:
    """Serialize to canonical JSON bytes.

    Rules are inherited from fingerprints.canonical_json_bytes().
    """

    return canonical_json_bytes(obj)
