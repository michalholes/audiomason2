from __future__ import annotations

from pathlib import Path


def test_badguys_public_api_discover_tests_import() -> None:
    # Backwards-compat import used by existing BadGuys tests.
    # Preferred import location.
    from badguys.discovery import discover_tests as _discover_tests2  # noqa: F401
    from badguys.tests import discover_tests as _discover_tests  # noqa: F401


def _repo_root() -> Path:
    # tests/ lives at repo root; resolve repo root deterministically.
    return Path(__file__).resolve().parents[1]


def _run_badguys_selected(*, include: list[str]) -> int:
    from badguys.run_suite import main as bg_main

    argv: list[str] = []
    for t in include:
        argv += ["--include", t]

    # Safety: never allow test_900 in these smoke checks.
    argv += ["--exclude", "test_900_commit_push_timestamp"]

    # Quiet console output to keep pytest logs clean.
    argv += ["-q"]

    return int(bg_main(argv))


def test_badguys_can_run_guard_test() -> None:
    rc = _run_badguys_selected(include=["test_000_test_mode_smoke"])
    assert rc == 0


def test_badguys_can_run_lock_test() -> None:
    # Second minimal end-to-end check to ensure infra works beyond discovery.
    rc = _run_badguys_selected(include=["test_001_lock_create_and_release"])
    assert rc == 0
