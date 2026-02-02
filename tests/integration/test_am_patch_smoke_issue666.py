import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ISSUE = "666"


def _ensure_patches_layout(repo_root: Path) -> Path:
    """
    In CI the whole patches/ tree is not present (and is typically gitignored),
    so the test must create the minimal layout it needs under repo_root/patches/.
    """
    patches_dir = repo_root / "patches"
    (patches_dir / "workspaces").mkdir(parents=True, exist_ok=True)
    (patches_dir / "logs").mkdir(parents=True, exist_ok=True)
    (patches_dir / "successful").mkdir(parents=True, exist_ok=True)
    (patches_dir / "unsuccessful").mkdir(parents=True, exist_ok=True)
    return patches_dir


def _cleanup(repo_root: Path) -> None:
    patches_dir = repo_root / "patches"

    # workspace
    shutil.rmtree(patches_dir / "workspaces" / f"issue_{ISSUE}", ignore_errors=True)

    # bundle
    try:
        (patches_dir / f"issue_{ISSUE}.zip").unlink()
    except FileNotFoundError:
        pass

    # successful / unsuccessful (delete only issue_666* artifacts)
    for d in ("successful", "unsuccessful"):
        base = patches_dir / d
        if base.exists():
            for p in base.glob(f"**/*issue_{ISSUE}*"):
                if p.is_file():
                    p.unlink()

    # logs (delete only am_patch_issue_666* logs)
    logs = patches_dir / "logs"
    if logs.exists():
        for p in logs.glob(f"am_patch_issue_{ISSUE}*"):
            if p.is_file():
                p.unlink()


def test_am_patch_smoke_issue_666() -> None:
    if os.environ.get("AM_PATCH_PYTEST_GATE") == "1":
        pytest.skip("skip runner smoke test inside am_patch pytest gate")

    repo_root = Path(__file__).resolve().parents[2]
    runner = repo_root / "scripts" / "am_patch.py"
    assert runner.exists(), "scripts/am_patch.py not found"

    # Ensure patches/ exists in CI and locally, then pre-clean to avoid false results.
    patches_dir = _ensure_patches_layout(repo_root)
    _cleanup(repo_root)

    # Create unified patch bundle exactly at patches/issue_666.zip
    bundle = patches_dir / f"issue_{ISSUE}.zip"

    patch_text = "\n".join(
        [
            "diff --git a/tests/smoke_issue666.txt b/tests/smoke_issue666.txt",
            "new file mode 100644",
            "index 0000000..e69de29",
            "--- /dev/null",
            "+++ b/tests/smoke_issue666.txt",
            "@@ -0,0 +1 @@",
            "+test",
            "",
        ]
    )

    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("issue_666a.patch", patch_text)

    # Run runner EXACTLY as required (no skips; gates must run).
    cmd = [
        sys.executable,
        str(runner),
        # "--test-mode",
        "-g",
        # "--skip-mypy",
        ISSUE,
        "test",
        str(bundle),
        "--test-mode",
        # "--skip-ruff",
        # "--skip-mypy",
    ]

    res = subprocess.run(
        cmd,
        cwd=str(repo_root),
        text=True,
        capture_output=True,
    )

    assert res.returncode == 0, f"Runner failed\nSTDOUT:\n{res.stdout}\n\nSTDERR:\n{res.stderr}"

    # Post-clean: remove any leftovers the runner might have produced in these dirs.
    _cleanup(repo_root)
