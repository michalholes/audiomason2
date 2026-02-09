import contextlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ISSUE = "999"


def _ensure_patches_layout(repo_root: Path) -> Path:
    patches_dir = repo_root / "patches"
    (patches_dir / "workspaces").mkdir(parents=True, exist_ok=True)
    (patches_dir / "logs").mkdir(parents=True, exist_ok=True)
    (patches_dir / "successful").mkdir(parents=True, exist_ok=True)
    (patches_dir / "unsuccessful").mkdir(parents=True, exist_ok=True)
    return patches_dir


def _cleanup(repo_root: Path) -> None:
    patches_dir = repo_root / "patches"

    shutil.rmtree(patches_dir / "workspaces" / f"issue_{ISSUE}", ignore_errors=True)

    with contextlib.suppress(FileNotFoundError):
        (patches_dir / f"issue_{ISSUE}.zip").unlink()
    with contextlib.suppress(FileNotFoundError):
        (patches_dir / f"issue_{ISSUE}_zero.zip").unlink()

    for d in ("successful", "unsuccessful"):
        base = patches_dir / d
        if base.exists():
            for p in base.glob(f"**/*issue_{ISSUE}*"):
                if p.is_file():
                    p.unlink()

    logs = patches_dir / "logs"
    if logs.exists():
        for p in logs.glob(f"am_patch_issue_{ISSUE}*"):
            if p.is_file():
                p.unlink()


def _run_runner(
    repo_root: Path, bundle: Path, extra: list[str]
) -> subprocess.CompletedProcess[str]:
    runner = repo_root / "scripts" / "am_patch.py"
    cmd = [
        sys.executable,
        str(runner),
        "--venv-bootstrap-mode",
        "never",
        ISSUE,
        "test apply-fail gates behavior",
        str(bundle),
        "--test-mode",
        "--skip-pytest",
        "--skip-mypy",
        "--skip-docs",
        *extra,
    ]
    return subprocess.run(cmd, cwd=str(repo_root), text=True, capture_output=True)


def test_gates_after_partial_apply_fail() -> None:
    if os.environ.get("AM_PATCH_PYTEST_GATE") == "1":
        pytest.skip("skip runner integration tests inside am_patch pytest gate")

    repo_root = Path(__file__).resolve().parents[2]
    patches_dir = _ensure_patches_layout(repo_root)
    _cleanup(repo_root)

    bundle = patches_dir / f"issue_{ISSUE}.zip"

    ok_patch = "\n".join(
        [
            "diff --git a/tests/_am_patch_partial_ok.txt b/tests/_am_patch_partial_ok.txt",
            "new file mode 100644",
            "index 0000000..e69de29",
            "--- /dev/null",
            "+++ b/tests/_am_patch_partial_ok.txt",
            "@@ -0,0 +1 @@",
            "+ok",
            "",
        ]
    )

    # This patch is guaranteed to fail (targets a file that does not exist).
    fail_patch = "\n".join(
        [
            "diff --git a/tests/_am_patch_nonexistent.txt b/tests/_am_patch_nonexistent.txt",
            "index 1111111..2222222 100644",
            "--- a/tests/_am_patch_nonexistent.txt",
            "+++ b/tests/_am_patch_nonexistent.txt",
            "@@ -1 +1 @@",
            "-nope",
            "+nope2",
            "",
        ]
    )

    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("issue_999_ok.patch", ok_patch)
        zf.writestr("issue_999_fail.patch", fail_patch)

    # Default: no gates after apply-fail.
    res = _run_runner(repo_root, bundle, extra=[])
    assert res.returncode != 0
    assert "DO: GATE_COMPILE" not in res.stdout

    # With flag: gates must run after partial apply-fail.
    res2 = _run_runner(repo_root, bundle, extra=["--gates-on-partial-apply"])
    assert res2.returncode != 0
    assert "DO: GATE_COMPILE" in res2.stdout

    _cleanup(repo_root)


def test_gates_after_zero_apply_fail() -> None:
    if os.environ.get("AM_PATCH_PYTEST_GATE") == "1":
        pytest.skip("skip runner integration tests inside am_patch pytest gate")

    repo_root = Path(__file__).resolve().parents[2]
    patches_dir = _ensure_patches_layout(repo_root)
    _cleanup(repo_root)

    bundle = patches_dir / f"issue_{ISSUE}_zero.zip"

    # This patch should fail immediately and apply nothing.
    fail_patch = "\n".join(
        [
            (
                "diff --git a/tests/_am_patch_zero_nonexistent.txt "
                "b/tests/_am_patch_zero_nonexistent.txt"
            ),
            "index 1111111..2222222 100644",
            "--- a/tests/_am_patch_zero_nonexistent.txt",
            "+++ b/tests/_am_patch_zero_nonexistent.txt",
            "@@ -1 +1 @@",
            "-nope",
            "+nope2",
            "",
        ]
    )

    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("issue_999_fail.patch", fail_patch)

    res = _run_runner(repo_root, bundle, extra=[])
    assert res.returncode != 0
    assert "DO: GATE_COMPILE" not in res.stdout

    res2 = _run_runner(repo_root, bundle, extra=["--gates-on-zero-apply"])
    assert res2.returncode != 0
    assert "DO: GATE_COMPILE" in res2.stdout

    _cleanup(repo_root)
