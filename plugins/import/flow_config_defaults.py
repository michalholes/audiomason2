"""FlowConfig defaults for the import plugin.

This module contains non-structural defaults only. It must not define step
order, graph edges, or any persisted legacy structural authority.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from plugins.file_io.service import FileService
from plugins.file_io.service.types import RootName

from .flow_config_validation import normalize_flow_config
from .storage import atomic_write_json_if_missing

DEFAULT_FLOW_CONFIG: dict[str, Any] = {
    "version": 1,
    "steps": {},
    "defaults": {},
}


def ensure_flow_config_exists(fs: FileService) -> dict[str, bool]:
    """Ensure the active FlowConfig exists under the wizards root."""
    normalized = normalize_flow_config(DEFAULT_FLOW_CONFIG)
    created = atomic_write_json_if_missing(
        fs,
        RootName.WIZARDS,
        "import/config/flow_config.json",
        normalized,
    )
    return {"flow_config_created": created}
