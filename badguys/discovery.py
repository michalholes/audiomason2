from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional

import tomllib


@dataclass(frozen=True)
class SuitePolicy:
    commit_limit: int
    guard_test_name: str
    require_guard_test: bool
    abort_on_guard_fail: bool


@dataclass(frozen=True)
class TestDef:
    name: str
    makes_commit: bool
    is_guard: bool
    run: Callable[..., object]


class TestList(List[TestDef]):
    # attach suite-level knobs used by runner
    commit_limit: int
    abort_on_guard_fail: bool


def _load_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _policy_from_config(repo_root: Path, config_path: Path, cli_commit_limit: Optional[int],
                        cli_include: list[str], cli_exclude: list[str]) -> tuple[SuitePolicy, list[str], list[str]]:
    raw = _load_toml(repo_root / config_path)
    suite = raw.get("suite", {})
    guard = raw.get("guard", {})
    filters = raw.get("filters", {})

    commit_limit = int(cli_commit_limit if cli_commit_limit is not None else suite.get("commit_limit", 1))
    require_guard_test = bool(guard.get("require_guard_test", True))
    guard_test_name = str(guard.get("guard_test_name", "test_000_test_mode_smoke"))
    abort_on_guard_fail = bool(guard.get("abort_on_guard_fail", True))

    include = list(filters.get("include", [])) + list(cli_include)
    exclude = list(filters.get("exclude", [])) + list(cli_exclude)

    return (
        SuitePolicy(
            commit_limit=commit_limit,
            guard_test_name=guard_test_name,
            require_guard_test=require_guard_test,
            abort_on_guard_fail=abort_on_guard_fail,
        ),
        include,
        exclude,
    )


def _load_test_from_file(path: Path) -> Optional[TestDef]:
    spec = importlib.util.spec_from_file_location(path.stem, str(path))
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    test = getattr(mod, "TEST", None)
    if not isinstance(test, dict):
        return None

    name = test.get("name")
    run = test.get("run")
    if not isinstance(name, str) or not callable(run):
        return None

    makes_commit = bool(test.get("makes_commit", False))
    is_guard = bool(test.get("is_guard", False))
    return TestDef(name=name, makes_commit=makes_commit, is_guard=is_guard, run=run)


def discover_tests(*, repo_root: Path, config_path: Path, cli_commit_limit: Optional[int],
                   cli_include: list[str], cli_exclude: list[str]) -> TestList:
    policy, include, exclude = _policy_from_config(repo_root, config_path, cli_commit_limit, cli_include, cli_exclude)

    tests_dir = repo_root / "badguys" / "tests"
    tests: list[TestDef] = []
    for p in sorted(tests_dir.glob("test_*.py")):
        t = _load_test_from_file(p)
        if t is not None:
            tests.append(t)

    all_tests = list(tests)

    # include/exclude conflict check
    if include and exclude:
        overlap = sorted(set(include).intersection(exclude))
        if overlap:
            joined = ", ".join(overlap)
            raise SystemExit(f"FAIL: include/exclude conflict: {joined}")

    # include filter
    if include:
        keep = set(include)
        tests = [t for t in tests if t.name in keep]

    # exclude filter
    if exclude:
        drop = set(exclude)
        tests = [t for t in tests if t.name not in drop]

    # ensure guard first if required
    if policy.require_guard_test:
        if policy.guard_test_name in set(exclude):
            raise SystemExit(f"FAIL: guard test excluded but required: {policy.guard_test_name}")

        if policy.guard_test_name not in {t.name for t in tests}:
            injected = next((t for t in all_tests if t.name == policy.guard_test_name), None)
            if injected is None:
                raise SystemExit(f"FAIL: guard test not found: {policy.guard_test_name}")
            tests = [injected] + tests

        guard = [t for t in tests if t.name == policy.guard_test_name]
        rest = [t for t in tests if t.name != policy.guard_test_name]
        tests = guard + rest

    out = TestList(tests)
    out.commit_limit = policy.commit_limit
    out.abort_on_guard_fail = policy.abort_on_guard_fail
    return out
