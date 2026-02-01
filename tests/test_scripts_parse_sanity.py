from __future__ import annotations

import ast
from pathlib import Path

import pytest


def _iter_script_files(repo_root: Path) -> list[Path]:
    scripts_dir = repo_root / "scripts"
    return sorted(p for p in scripts_dir.rglob("*.py") if p.is_file())


@pytest.mark.parametrize("path", _iter_script_files(Path(__file__).resolve().parents[1]))
def test_scripts_are_parseable(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    ast.parse(text, filename=str(path))
