import subprocess
import sys
import zipfile
from pathlib import Path
import shutil


ISSUE = "666"


def _cleanup(repo_root: Path) -> None:
    # workspace
    shutil.rmtree(repo_root / "patches" / "workspaces" / f"issue_{ISSUE}", ignore_errors=True)

    # bundle
    try:
        (repo_root / "patches" / f"issue_{ISSUE}.zip").unlink()
    except FileNotFoundError:
        pass

    # successful / unsuccessful
    for d in ("successful", "unsuccessful"):
        base = repo_root / "patches" / d
        if base.exists():
            for p in base.glob(f"**/*issue_{ISSUE}*"):
                if p.is_file():
                    p.unlink()

    # logs
    logs = repo_root / "patches" / "logs"
    if logs.exists():
        for p in logs.glob(f"am_patch_issue_{ISSUE}*"):
            if p.is_file():
                p.unlink()


def test_am_patch_smoke_issue_666():
    repo_root = Path(__file__).resolve().parents[2]
    runner = repo_root / "scripts" / "am_patch.py"

    assert runner.exists(), "am_patch.py not found"

    # PRE-CLEAN (avoid false positive / negative)
    _cleanup(repo_root)

    # Create unified patch bundle in patches/
    bundle = repo_root / "patches" / f"issue_{ISSUE}.zip"

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

    # Run runner EXACTLY as required
    cmd = [
        sys.executable,
        str(runner),
        ISSUE,
        "test",
        str(bundle),
        "--test-mode",
    ]

    res = subprocess.run(
        cmd,
        cwd=str(repo_root),
        text=True,
        capture_output=True,
    )

    assert res.returncode == 0, (
        "Runner failed\n"
        f"STDOUT:\n{res.stdout}\n\n"
        f"STDERR:\n{res.stderr}"
    )

    # POST-CLEAN
    _cleanup(repo_root)

