"""WizardService: CRUD and validation for wizards outside the repository."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from audiomason.core.errors import ConfigError


def _default_wizards_dir() -> Path:
    return Path.home() / ".config/audiomason/wizards"


@dataclass(frozen=True)
class WizardInfo:
    name: str
    path: Path


class WizardService:
    """Manage wizard YAML definitions stored in the user config area."""

    def __init__(self, wizards_dir: Path | None = None) -> None:
        self._dir = wizards_dir or _default_wizards_dir()

    @property
    def wizards_dir(self) -> Path:
        return self._dir

    def list_wizards(self) -> list[WizardInfo]:
        self._dir.mkdir(parents=True, exist_ok=True)
        infos: list[WizardInfo] = []
        for p in sorted(self._dir.glob("*.yaml")):
            if p.is_file():
                infos.append(WizardInfo(name=p.stem, path=p))
        return infos

    def get_wizard_text(self, name: str) -> str:
        p = self._wizard_path(name)
        if not p.exists():
            raise ConfigError(f"Wizard not found: {name}")
        return p.read_text(encoding="utf-8")

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

        p = self._wizard_path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        # Store as provided to preserve user formatting, but enforce ASCII.
        try:
            yaml_text.encode("ascii")
        except UnicodeEncodeError as e:
            raise ConfigError("Wizard YAML must be ASCII-only") from e
        p.write_text(yaml_text, encoding="utf-8")

    def delete_wizard(self, name: str) -> None:
        p = self._wizard_path(name)
        if not p.exists():
            raise ConfigError(f"Wizard not found: {name}")
        p.unlink()

    def _wizard_path(self, name: str) -> Path:
        safe = "".join(ch if (ch.isalnum() or ch in "_-") else "_" for ch in name)
        if not safe:
            raise ConfigError("Invalid wizard name")
        return self._dir / f"{safe}.yaml"
