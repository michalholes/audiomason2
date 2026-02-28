from __future__ import annotations

from pathlib import Path

from badguys.run_suite import _prepare_hermetic_live_repo


def test_hermetic_live_repo_uses_real_patches_dir(tmp_path: Path) -> None:
    # Minimal repo root content; _prepare_hermetic_live_repo performs a copy + git init.
    (tmp_path / "README.txt").write_text("hermetic repo test\n", encoding="utf-8")

    live_repo = _prepare_hermetic_live_repo(tmp_path)
    patches_dir = live_repo / "patches"

    assert patches_dir.exists()
    assert not patches_dir.is_symlink()

    for rel in [
        "logs",
        "workspaces",
        "successful",
        "unsuccessful",
        "_test_mode",
    ]:
        assert (patches_dir / rel).is_dir()