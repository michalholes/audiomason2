from __future__ import annotations

from pathlib import Path

from badguys._util import Plan
from badguys.tests import discover_tests


def run(ctx):
    cfg_path = Path("badguys/config.toml")
    guard = "test_000_test_mode_smoke"
    target = "test_030_show_config"

    tests = discover_tests(
        repo_root=ctx.repo_root,
        config_path=cfg_path,
        cli_commit_limit=None,
        cli_include=[guard, target],
        cli_exclude=[],
    )

    names = [t.name for t in tests]
    assert names == [guard, target], f"FAIL: include_single expected {[guard, target]!r}, got {names!r}"
    return Plan(steps=[])


TEST = {
    "name": "test_011_include_single",
    "run": run,
}
