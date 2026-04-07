"""Load the effective model snapshot for an active import session.

ASCII-only.
"""

from __future__ import annotations

import json
from typing import Any

from plugins.file_io.service import FileService
from plugins.file_io.service.types import RootName


class EffectiveModelJsonError(RuntimeError):
    def __init__(self, message: str, *, rel_path: str):
        super().__init__(message)
        self.rel_path = rel_path


def load_effective_model_json(*, fs: FileService, session_id: str) -> dict[str, Any]:
    rel_path = f"import/sessions/{session_id}/effective_model.json"
    try:
        with fs.open_read(RootName.WIZARDS, rel_path) as handle:
            raw = handle.read()
    except FileNotFoundError as exc:
        raise EffectiveModelJsonError("effective_model.json is missing", rel_path=rel_path) from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise EffectiveModelJsonError(
            "effective_model.json is invalid JSON",
            rel_path=rel_path,
        ) from exc
    if not isinstance(payload, dict):
        raise EffectiveModelJsonError("effective_model.json must be an object", rel_path=rel_path)
    return payload
