from __future__ import annotations

from badguys.tests import discover_tests


def run(ctx):
    tests1 = discover_tests(
        repo_root=ctx.repo_root,
        config_path=ctx.cfg.config_path,
        cli_commit_limit=None,
        cli_include=[],
        cli_exclude=[],
    )
    tests2 = discover_tests(
        repo_root=ctx.repo_root,
        config_path=ctx.cfg.config_path,
        cli_commit_limit=None,
        cli_include=[],
        cli_exclude=[],
    )

    names1 = [t.name for t in tests1]
    names2 = [t.name for t in tests2]
    assert names1 == names2, "FAIL: discovery order is not deterministic"

    # Guard is forced first; ensure the rest is lexicographic by filename (indirectly).
    # We validate by comparing to the sorted test module list.
    tests_dir = ctx.repo_root / "badguys" / "tests"
    file_names = [p.stem for p in sorted(tests_dir.glob("test_*.py"))]
    assert file_names, "FAIL: no tests discovered in filesystem"

    # Map filename -> discovered name by loading via discover_tests itself order. Since
    # discover_tests already sorts by filename, the non-guard portion must match that order.
    guard = ctx.cfg.guard_test_name
    non_guard = [n for n in names1 if n != guard]
    # Build expected name order by loading modules in sorted filename order.
    expected = []
    for p in sorted(tests_dir.glob("test_*.py")):
        if p.stem == guard:
            continue
        # discover_tests loader uses TEST["name"] which matches p.stem for our suite.
        expected.append(p.stem)
    # Some tests may have TEST["name"] different from filename; only assert when they match.
    if all(n in file_names for n in non_guard) and all(n in file_names for n in expected):
        assert non_guard == expected, "FAIL: non-guard test order is not lexicographic by filename"

    return []


TEST = {
    "name": "test_010_discovery_deterministic_order",
    "run": run,
}
