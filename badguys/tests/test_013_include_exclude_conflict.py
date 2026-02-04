from __future__ import annotations

from pathlib import Path

from badguys._util import Plan
from badguys.tests import discover_tests


def run(ctx):
    cfg_path = Path("badguys/config.toml")
    guard = "test_000_test_mode_smoke"
    target = "test_030_show_config"

    try:
        discover_tests(
            repo_root=ctx.repo_root,
            config_path=cfg_path,
            cli_commit_limit=None,
            cli_include=[target],
            cli_exclude=[target],
        )
    except SystemExit as e:
        msg = str(e)
        assert "FAIL:" in msg, f"FAIL: expected FAIL message, got: {msg!r}"
        assert "guard test not found" in msg, f"FAIL: expected guard-not-found, got: {msg!r}"
        assert guard in msg, f"FAIL: expected guard name in message, got: {msg!r}"
        return Plan(steps=[])

    raise AssertionError("FAIL: expected deterministic SystemExit on include/exclude conflict")


TEST = {
    "name": "test_013_include_exclude_conflict",
    "run": run,
}
