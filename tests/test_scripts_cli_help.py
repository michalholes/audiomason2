from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "rel_script, extra_env",
    [
        ("scripts/am_patch.py", {"AM_PATCH_VENV_BOOTSTRAPPED": "1"}),
        ("scripts/gov_versions.py", {}),
        ("scripts/sync_issues_archive.py", {}),
    ],
)
def test_scripts_help_smoke(rel_script: str, extra_env: dict[str, str]) -> None:
    repo_root = _repo_root()
    script_path = repo_root / rel_script
    assert script_path.exists(), f"missing script: {rel_script}"

    env = os.environ.copy()
    env.update(extra_env)

    p = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0, f"help failed for {rel_script}: rc={p.returncode}\n{out}"
    assert out.strip(), f"no help output for {rel_script}"
