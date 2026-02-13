from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .compat import import_legacy
from .deps import Deps
from .model import RunnerError


@dataclass(frozen=True)
class GateSpec:
    name: str
    argv: tuple[str, ...]


def run_gate_specs(deps: Deps, cwd: Path, specs: Sequence[GateSpec]) -> None:
    for s in specs:
        res = deps.runner.run(list(s.argv), cwd=cwd)
        if res.returncode != 0:
            msg = res.stderr.strip() or res.stdout.strip()
            raise RunnerError(f"Gate failed: {s.name}: {msg}")


# ---------------------------------------------------------------------------
# Legacy compatibility: scripts/am_patch.py imports run_gates/run_badguys from
# am_patch.gates. This repo-root module must preserve that API.
# ---------------------------------------------------------------------------

try:
    _legacy = import_legacy("gates")
    run_gates = _legacy.run_gates  # type: ignore[attr-defined]
    run_badguys = _legacy.run_badguys  # type: ignore[attr-defined]
    check_docs_gate = _legacy.check_docs_gate  # type: ignore[attr-defined]
except Exception:
    pass
