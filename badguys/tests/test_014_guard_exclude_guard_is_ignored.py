from __future__ import annotations

from pathlib import Path

from badguys._util import Plan
from badguys.tests import discover_tests


def run(ctx) -> Plan:
    cfg_path = Path("badguys/config.toml")
    guard = "test_000_test_mode_smoke"

    tests = discover_tests(
        repo_root=ctx.repo_root,
        config_path=cfg_path,
        cli_commit_limit=None,
        cli_include=[],
        cli_exclude=[guard],
    )

    names = [t.name for t in tests]
    assert guard in names, f"FAIL: guard was excluded but must be forced: {guard}"
    assert names[0] == guard, f"FAIL: guard not first after exclude attempt: got {names[0]!r}"
    return Plan(steps=[])


TEST = {
    "name": "test_014_guard_exclude_guard_is_ignored",
    "run": run,
}
