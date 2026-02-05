from __future__ import annotations

from pathlib import Path

from badguys._util import Plan
from badguys.tests import discover_tests


def run(ctx) -> Plan:
    cfg_path = Path("badguys/config.toml")
    guard = "test_000_test_mode_smoke"

    try:
        discover_tests(
            repo_root=ctx.repo_root,
            config_path=cfg_path,
            cli_commit_limit=None,
            cli_include=[],
            cli_exclude=[guard],
        )
    except SystemExit as e:
        msg = str(e)
        needle = f"guard test excluded but required: {guard}"
        assert needle in msg, f"expected {needle!r} in error: {msg!r}"
        return Plan(steps=[])

    raise AssertionError("expected SystemExit when excluding required guard test")


TEST = {
    "name": "test_014_guard_exclude_guard_is_ignored",
    "run": run,
}
