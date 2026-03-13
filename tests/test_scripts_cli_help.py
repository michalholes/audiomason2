from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _configured_pytest_routing_mode(repo_root: Path) -> str:
    config_path = repo_root / "scripts" / "am_patch" / "am_patch.toml"
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    flat: dict[str, object] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            for subkey, subvalue in value.items():
                flat[str(subkey)] = subvalue
        else:
            flat[str(key)] = value
    return str(flat.get("pytest_routing_mode", "bucketed"))


@pytest.mark.parametrize(
    "rel_script, extra_env",
    [
        ("scripts/am_patch.py", {"AM_PATCH_VENV_BOOTSTRAPPED": "1"}),
        ("scripts/check_patch_pm.py", {}),
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


def test_am_patch_help_all_mentions_pytest_routing_mode() -> None:
    repo_root = _repo_root()
    script_path = repo_root / "scripts" / "am_patch.py"

    env = os.environ.copy()
    env["AM_PATCH_VENV_BOOTSTRAPPED"] = "1"

    p = subprocess.run(
        [sys.executable, str(script_path), "--help-all"],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0, out
    assert "--pytest-routing-mode legacy|bucketed" in out


def test_am_patch_show_config_prints_pytest_routing_keys() -> None:
    repo_root = _repo_root()
    script_path = repo_root / "scripts" / "am_patch.py"

    env = os.environ.copy()
    env["AM_PATCH_VENV_BOOTSTRAPPED"] = "1"

    p = subprocess.run(
        [sys.executable, str(script_path), "--show-config"],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    out = (p.stdout or "") + (p.stderr or "")
    assert p.returncode == 0, out

    expected_mode = _configured_pytest_routing_mode(repo_root)
    assert f"pytest_routing_mode={expected_mode!r}" in out
    assert "pytest_smoke_targets=" in out
    assert "pytest_area_targets=" in out
