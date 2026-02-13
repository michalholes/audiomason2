from __future__ import annotations

from pathlib import Path

import pytest
from am_patch.model import RunnerError

from am_patch.promote import promote_from_workspace


def test_promote_from_workspace_copies_file(tmp_path: Path, fake_deps) -> None:
    ws_repo = tmp_path / "ws" / "repo"
    live_repo = tmp_path / "live"
    ws_repo.mkdir(parents=True)
    live_repo.mkdir()

    (ws_repo / "a.txt").write_text("A\n", encoding="utf-8")
    promote_from_workspace(ws_repo, live_repo, fake_deps, ("a.txt",))
    assert (live_repo / "a.txt").read_text(encoding="utf-8") == "A\n"


def test_promote_missing_source_raises(tmp_path: Path, fake_deps) -> None:
    ws_repo = tmp_path / "ws" / "repo"
    live_repo = tmp_path / "live"
    ws_repo.mkdir(parents=True)
    live_repo.mkdir()

    with pytest.raises(RunnerError):
        promote_from_workspace(ws_repo, live_repo, fake_deps, ("missing.txt",))
