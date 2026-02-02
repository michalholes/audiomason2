import subprocess
import sys
from pathlib import Path


def test_am_patch_runs_and_prints_version():
    """
    Smoke test: overí, že runner sa dá spustiť a vypíše verziu.
    Neoveruje konkrétne číslo verzie, iba že výstup nie je prázdny
    a návratový kód je 0.
    """
    repo_root = Path(__file__).resolve().parents[1]
    runner = repo_root / "scripts" / "am_patch.py"

    assert runner.exists(), "scripts/am_patch.py not found"

    proc = subprocess.run(
        [sys.executable, str(runner), "--version"],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, f"runner exited with {proc.returncode}, stderr={proc.stderr!r}"
    assert proc.stdout.strip(), "runner --version produced empty output"
