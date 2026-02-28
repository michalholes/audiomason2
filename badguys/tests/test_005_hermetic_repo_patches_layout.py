from __future__ import annotations

import tempfile
from pathlib import Path

from badguys._util import FuncStep, Plan
from badguys.run_suite import _prepare_hermetic_live_repo


def run(ctx) -> Plan:
    def _check() -> None:
        with tempfile.TemporaryDirectory(prefix="badguys_hermetic_repo_") as td:
            tmp_path = Path(td)

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

    return Plan(steps=[FuncStep(name="check_hermetic_repo_patches_layout", fn=_check)])


TEST = {
    "name": "test_005_hermetic_repo_patches_layout",
    "run": run,
}
