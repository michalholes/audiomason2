from __future__ import annotations

from pathlib import Path

from badguys.tests import discover_tests


def run(ctx):
    cfg_path = Path("badguys/config.toml")
    guard = "test_000_test_mode_smoke"
    target = "test_030_show_config"

    tests = discover_tests(
        repo_root=ctx.repo_root,
        config_path=cfg_path,
        cli_commit_limit=None,
        cli_include=[],
        cli_exclude=[target],
    )

    names = [t.name for t in tests]
    assert guard in names, f"FAIL: guard missing: {guard}"
    assert names[0] == guard, f"FAIL: guard not first: got {names[0]!r}"
    assert target not in names, f"FAIL: exclude_single still included target: {target}"
    return []


TEST = {
    "name": "test_012_exclude_single",
    "run": run,
}
