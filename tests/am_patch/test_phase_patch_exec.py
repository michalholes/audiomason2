from __future__ import annotations

from pathlib import Path

import pytest
from am_patch.model import RunnerError

from am_patch.patch_exec import _extract_changed_paths_from_unified, apply_patch


def test_extract_changed_paths() -> None:
    diff = (
        "diff --git a/a.txt b/a.txt\ndiff --git a/b/c.txt b/b/c.txt\ndiff --git a/a.txt b/a.txt\n"
    )
    assert _extract_changed_paths_from_unified(diff) == ["a.txt", "b/c.txt"]


def test_apply_patch_from_zip_applies_changes(
    repo_root: Path, fake_deps, make_unified_patch, make_patch_zip
) -> None:
    unified = make_unified_patch("x.txt", before="one\n", after="two\n")
    patch_zip = make_patch_zip("x.txt", unified)

    res = apply_patch(repo_root, patch_zip, fake_deps)
    assert res.changed_paths == ("x.txt",)
    assert (repo_root / "x.txt").read_text(encoding="utf-8") == "two\n"


def test_apply_patch_raises_on_git_apply_failure(
    repo_root: Path, fake_deps, make_unified_patch, make_patch_zip
) -> None:
    unified = make_unified_patch("x.txt", before="one\n", after="two\n")
    patch_zip = make_patch_zip("x.txt", unified)

    # Corrupt the file to force our minimal applier to fail.
    (repo_root / "x.txt").write_text("DIFFERS\n", encoding="utf-8")

    with pytest.raises(RunnerError):
        apply_patch(repo_root, patch_zip, fake_deps)
