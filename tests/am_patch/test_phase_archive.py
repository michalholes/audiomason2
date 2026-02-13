from __future__ import annotations

import zipfile
from pathlib import Path

from am_patch.archive import create_archives


def test_create_archives_creates_placeholder_zips(repo_root: Path) -> None:
    res = create_archives(repo_root, "802", include_success=True)
    assert res.patched_zip is not None
    assert res.success_zip is not None
    assert res.patched_zip.exists()
    assert res.success_zip.exists()

    with zipfile.ZipFile(res.patched_zip, "r") as z:
        assert "README.txt" in z.namelist()
