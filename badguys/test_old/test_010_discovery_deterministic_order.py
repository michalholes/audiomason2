from __future__ import annotations

from pathlib import Path

from badguys._util import FuncStep, Plan
from badguys.tests import discover_tests


def run(ctx) -> Plan:
    cfg_path = Path("badguys/config.toml")

    def _check() -> None:
        tests1 = discover_tests(
            repo_root=ctx.repo_root,
            config_path=cfg_path,
            cli_commit_limit=None,
            cli_include=[],
            cli_exclude=[],
        )
        tests2 = discover_tests(
            repo_root=ctx.repo_root,
            config_path=cfg_path,
            cli_commit_limit=None,
            cli_include=[],
            cli_exclude=[],
        )

        names1 = [t.name for t in tests1]
        names2 = [t.name for t in tests2]
        assert names1 == names2, "FAIL: discovery order is not deterministic"

        tests_dir = ctx.repo_root / "badguys" / "tests"
        file_stems = [p.stem for p in sorted(tests_dir.glob("test_*.py"))]
        assert file_stems, "FAIL: no tests discovered in filesystem"

        guard = "test_000_test_mode_smoke"
        assert guard in names1, f"FAIL: expected guard test present: {guard}"
        assert names1[0] == guard, f"FAIL: guard test not first: got {names1[0]!r}"

        expected = [guard] + [s for s in file_stems if s != guard]
        assert names1 == expected, "FAIL: discovered test order is not lexicographic by filename"

    return Plan(steps=[FuncStep(name="check_discovery_order", fn=_check)])


TEST = {
    "name": "test_010_discovery_deterministic_order",
    "run": run,
}
