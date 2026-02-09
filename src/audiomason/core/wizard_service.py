"""WizardService: CRUD and validation for wizard definitions.

All filesystem operations MUST go through the file_io capability (FileService).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

from audiomason.core.config import ConfigResolver
from audiomason.core.errors import ConfigError

_DEFINITIONS_DIR = "definitions"


@dataclass(frozen=True)
class WizardInfo:
    name: str


class WizardService:
    """Manage wizard YAML definitions stored under the file_io `wizards` root.

    Wizard definitions are stored under: <wizards_root>/definitions/<name>.yaml
    """

    def __init__(self, file_service: FileService | None = None) -> None:
        if file_service is not None:
            self._fs = file_service
        else:
            resolver = ConfigResolver()
            self._fs = FileService.from_resolver(resolver)

        # Ensure the definitions directory exists.
        if not self._fs.exists(RootName.WIZARDS, _DEFINITIONS_DIR):
            self._fs.mkdir(RootName.WIZARDS, _DEFINITIONS_DIR, parents=True, exist_ok=True)

    @property
    def wizards_dir(self) -> Path:
        return self._fs.root_dir(RootName.WIZARDS)

    def list_wizards(self) -> list[WizardInfo]:
        entries = self._fs.list_dir(RootName.WIZARDS, _DEFINITIONS_DIR, recursive=False)
        names: list[str] = []
        for e in entries:
            if e.is_dir:
                continue
            if not e.rel_path.startswith(f"{_DEFINITIONS_DIR}/"):
                continue
            filename = e.rel_path.split("/", 1)[1]
            if "/" in filename:
                # Only accept direct children of definitions/
                continue
            if not filename.endswith(".yaml"):
                continue
            stem = filename[: -len(".yaml")]
            if stem:
                names.append(stem)
        names.sort()
        return [WizardInfo(name=n) for n in names]

    def get_wizard_text(self, name: str) -> str:
        rel = self._wizard_rel_path(name)
        if not self._fs.exists(RootName.WIZARDS, rel):
            raise ConfigError(f"Wizard not found: {name}")
        with self._fs.open_read(RootName.WIZARDS, rel) as f:
            return f.read().decode("utf-8")

    def put_wizard_text(self, name: str, yaml_text: str) -> None:
        # Validate basic YAML structure.
        try:
            obj = yaml.safe_load(yaml_text)
        except Exception as e:
            raise ConfigError(f"Invalid wizard YAML: {e}") from e
        if obj is None:
            obj = {}
        if not isinstance(obj, dict):
            raise ConfigError("Wizard YAML must be a mapping")

        # Store as provided to preserve user formatting, but enforce ASCII.
        try:
            yaml_text.encode("ascii")
        except UnicodeEncodeError as e:
            raise ConfigError("Wizard YAML must be ASCII-only") from e

        rel = self._wizard_rel_path(name)
        with self._fs.open_write(
            RootName.WIZARDS,
            rel,
            overwrite=True,
            mkdir_parents=True,
        ) as f:
            f.write(yaml_text.encode("utf-8"))

    def delete_wizard(self, name: str) -> None:
        rel = self._wizard_rel_path(name)
        if not self._fs.exists(RootName.WIZARDS, rel):
            raise ConfigError(f"Wizard not found: {name}")
        self._fs.delete_file(RootName.WIZARDS, rel)

    def _wizard_rel_path(self, name: str) -> str:
        safe = "".join(ch if (ch.isalnum() or ch in "_-") else "_" for ch in name)
        if not safe:
            raise ConfigError("Invalid wizard name")
        return f"{_DEFINITIONS_DIR}/{safe}.yaml"
