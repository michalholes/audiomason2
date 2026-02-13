from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def _iter_script_files(repo_root: Path) -> list[Path]:
    scripts_dir = repo_root / "scripts"
    return sorted(p for p in scripts_dir.rglob("*.py") if p.is_file())


@pytest.mark.parametrize("path", _iter_script_files(Path(__file__).resolve().parents[1]))
def test_scripts_are_parseable(path: Path) -> None:
    # Run compilation in a fresh interpreter process to avoid flaky
    # interpreter state leaking across tests.
    proc = subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        stdout = proc.stdout.strip()
        msg = "\n".join(
            s
            for s in [
                f"py_compile failed for: {path}",
                f"returncode={proc.returncode}",
                f"stdout:\n{stdout}" if stdout else "",
                f"stderr:\n{stderr}" if stderr else "",
            ]
            if s
        )
        raise AssertionError(msg)
