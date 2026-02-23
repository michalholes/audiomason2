"""WizardDefinition editor storage helpers (plugin: import).

Provides canonical JSON load/save for WizardDefinition under the WIZARDS root.

Rules:
- canonical JSON (UTF-8, ensure_ascii, sort keys, newline)
- atomic write (temp + rename)
- validate before save

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from plugins.file_io.service import FileService
from plugins.file_io.service.types import RootName

from .storage import atomic_write_json, read_json
from .wizard_definition_model import (
    WIZARD_DEFINITION_REL_PATH,
    validate_wizard_definition_structure,
)


def load_wizard_definition(fs: FileService) -> Any:
    wd = read_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH)
    validate_wizard_definition_structure(wd)
    return wd


def save_wizard_definition(fs: FileService, obj: Any) -> None:
    validate_wizard_definition_structure(obj)
    atomic_write_json(fs, RootName.WIZARDS, WIZARD_DEFINITION_REL_PATH, obj)
