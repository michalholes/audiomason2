from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _scripts_dir() -> Path:
    return _repo_root() / "scripts"


def _am_patch_module_names() -> list[str]:
    pkg_dir = _scripts_dir() / "am_patch"
    names: list[str] = []
    for p in sorted(pkg_dir.glob("*.py")):
        if p.name == "__init__.py":
            continue
        names.append(f"am_patch.{p.stem}")
    return names


def _top_level_module_names() -> list[str]:
    # NOTE: Do not import scripts/am_patch.py; it can execv into repo/.venv.
    return [
        "gov_versions",
        "sync_issues_archive",
    ]


def _ensure_scripts_on_path() -> None:
    scripts_dir = _scripts_dir()
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


@pytest.mark.parametrize("mod", _am_patch_module_names() + _top_level_module_names())
def test_scripts_modules_import_cleanly(mod: str) -> None:
    _ensure_scripts_on_path()
    importlib.import_module(mod)
