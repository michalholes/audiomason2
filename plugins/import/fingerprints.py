"""Fingerprint utilities for import wizard engine.

ASCII-only.
"""

from __future__ import annotations

import hashlib
import json


def canonical_json_bytes(obj: object) -> bytes:
    """Return canonical JSON bytes for deterministic fingerprinting.

    Rules:
    - ensure_ascii=True
    - separators without spaces
    - sort_keys=True
    """
    text = json.dumps(
        obj,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return text.encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fingerprint_json(obj: object) -> str:
    return sha256_hex(canonical_json_bytes(obj))
