from __future__ import annotations

from pathlib import Path

import pytest
from am_patch.model import RunnerError

from am_patch.gates import GateSpec, run_gate_specs


def test_run_gate_specs_happy_path(repo_root: Path, fake_deps) -> None:
    run_gate_specs(fake_deps, repo_root, [GateSpec(name="ok", argv=("pytest", "-q"))])


def test_run_gate_specs_failure_raises(repo_root: Path, fake_deps) -> None:
    # Fail the first gate.
    fake_deps.runner.set_failure(("pytest",), stderr="boom")
    with pytest.raises(RunnerError):
        run_gate_specs(fake_deps, repo_root, [GateSpec(name="pytest", argv=("pytest", "-q"))])
