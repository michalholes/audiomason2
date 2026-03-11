from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/pm_validator_artifact.py"
COMMIT = "Add repo PM validator artifact"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _git_patch(relpath: str, old_text: str | None, new_text: str | None) -> bytes:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        old = root / "old" / relpath
        new = root / "new" / relpath
        if old_text is not None:
            _write(old, old_text)
        else:
            old.parent.mkdir(parents=True, exist_ok=True)
        if new_text is not None:
            _write(new, new_text)
        else:
            new.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [
                "git",
                "diff",
                "--no-index",
                "--src-prefix=a/",
                "--dst-prefix=b/",
                str(old.relative_to(root)),
                str(new.relative_to(root)),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 1, proc.stderr
        patch = proc.stdout.replace(f"a/old/{relpath}", f"a/{relpath}")
        patch = patch.replace(f"b/new/{relpath}", f"b/{relpath}")
        return patch.encode("utf-8")


def _safe_member(relpath: str) -> str:
    return "patches/per_file/" + relpath.replace("/", "__") + ".patch"


def _write_zip(path: Path, members: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def _patch_zip(path: Path, patch_member: str, patch_bytes: bytes, *, issue: str = "601") -> None:
    _write_zip(
        path,
        {
            "COMMIT_MESSAGE.txt": (COMMIT + "\n").encode("utf-8"),
            "ISSUE_NUMBER.txt": (issue + "\n").encode("utf-8"),
            patch_member: patch_bytes,
        },
    )


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_initial_mode_passes(tmp_path: Path) -> None:
    relpath = "scripts/sample.py"
    before = "def value():\n    return 1\n"
    after = "def value():\n    return 2\n"
    snapshot = tmp_path / "workspace.zip"
    patch_zip = tmp_path / "issue_601_v2.zip"
    _write_zip(snapshot, {relpath: before.encode("utf-8")})
    _patch_zip(patch_zip, _safe_member(relpath), _git_patch(relpath, before, after))

    proc = _run("601", COMMIT, str(patch_zip), "--workspace-snapshot", str(snapshot))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "RESULT: PASS" in proc.stdout
    assert "RULE MONOLITH: PASS" in proc.stdout


def test_repair_overlay_only_passes(tmp_path: Path) -> None:
    relpath = "scripts/sample.py"
    before = "def value():\n    return 2\n"
    after = "def value():\n    return 3\n"
    overlay = tmp_path / "patched_issue601_v1.zip"
    patch_zip = tmp_path / "issue_601_v2.zip"
    _write_zip(overlay, {relpath: before.encode("utf-8")})
    _patch_zip(patch_zip, _safe_member(relpath), _git_patch(relpath, before, after))

    proc = _run("601", COMMIT, str(patch_zip), "--repair-overlay", str(overlay))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "RESULT: PASS" in proc.stdout
    assert "RULE GIT_APPLY_CHECK:patches/per_file/scripts__sample.py.patch: PASS" in proc.stdout


def test_repair_supplemental_file_is_supported(tmp_path: Path) -> None:
    relpath = "tests/test_sample.txt"
    before = "a\n"
    after = "b\n"
    snapshot = tmp_path / "workspace.zip"
    overlay = tmp_path / "patched_issue601_v1.zip"
    patch_zip = tmp_path / "issue_601_v2.zip"
    _write_zip(snapshot, {relpath: before.encode("utf-8")})
    _write_zip(overlay, {"scripts/sample.py": b"def value():\n    return 2\n"})
    _patch_zip(patch_zip, _safe_member(relpath), _git_patch(relpath, before, after))

    proc = _run(
        "601",
        COMMIT,
        str(patch_zip),
        "--repair-overlay",
        str(overlay),
        "--workspace-snapshot",
        str(snapshot),
        "--supplemental-file",
        relpath,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "RESULT: PASS" in proc.stdout


def test_repair_without_required_supplemental_file_fails(tmp_path: Path) -> None:
    relpath = "tests/test_sample.txt"
    before = "a\n"
    after = "b\n"
    snapshot = tmp_path / "workspace.zip"
    overlay = tmp_path / "patched_issue601_v1.zip"
    patch_zip = tmp_path / "issue_601_v2.zip"
    _write_zip(snapshot, {relpath: before.encode("utf-8")})
    _write_zip(overlay, {})
    _patch_zip(patch_zip, _safe_member(relpath), _git_patch(relpath, before, after))

    proc = _run(
        "601",
        COMMIT,
        str(patch_zip),
        "--repair-overlay",
        str(overlay),
        "--workspace-snapshot",
        str(snapshot),
    )
    assert proc.returncode == 1
    expected = (
        "RULE VALIDATION_ERROR: FAIL - repair_requires_supplemental_file:['tests/test_sample.txt']"
    )
    assert expected in proc.stdout
