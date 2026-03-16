"""Shipped default WizardDefinition v3 bootstrap source for import CLI.

ASCII-only.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

_DEFAULT_WIZARD_SOURCE_PATH = Path(__file__).with_name("default_wizard_v3_source.json")


def _load_default_wizard_definition_v3_source() -> dict[str, Any]:
    raw = json.loads(_DEFAULT_WIZARD_SOURCE_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError("default WizardDefinition v3 source must be an object")
    return raw


def build_default_wizard_definition_v3() -> dict[str, Any]:
    """Return the shipped default WizardDefinition v3 bootstrap seed."""

    return deepcopy(_load_default_wizard_definition_v3_source())


__all__ = ["build_default_wizard_definition_v3"]
