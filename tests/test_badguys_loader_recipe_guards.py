from pathlib import Path

import pytest
from badguys.bdg_loader import load_bdg_test


def test_loader_rejects_step_level_recipe_keys(tmp_path: Path) -> None:
    path = tmp_path / "test_guard.bdg"
    path.write_text(
        """
[meta]
makes_commit = false
is_guard = false

[[step]]
op = "BUILD_CFG"
cli_runner_verbosity = "debug"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="step-level recipe moved"):
        load_bdg_test(path)
