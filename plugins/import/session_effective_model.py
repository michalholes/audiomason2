"""Load the effective model snapshot for an active import session.

ASCII-only.
"""

from __future__ import annotations

import json
from pathlib import Path


class EffectiveModelJsonError(RuntimeError):
    def __init__(self, message: str, *, path: Path):
        super().__init__(message)
        self.path = path


def load_effective_model_json(session_dir: Path) -> dict:
    """Load sessions/<sid>/effective_model.json from session_dir.

    Raises EffectiveModelJsonError on missing file or invalid JSON.
    """

    path = session_dir / "effective_model.json"
    try:
        raw = path.read_bytes()
    except FileNotFoundError as e:
        raise EffectiveModelJsonError("effective_model.json is missing", path=path) from e
    try:
        obj = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise EffectiveModelJsonError("effective_model.json is invalid JSON", path=path) from e
    if not isinstance(obj, dict):
        raise EffectiveModelJsonError("effective_model.json must be an object", path=path)
    return obj
