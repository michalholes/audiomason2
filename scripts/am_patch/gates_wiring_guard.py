from __future__ import annotations

import ast
from pathlib import Path

from .errors import RunnerError

_ALLOWED_CALLSITE = "scripts/am_patch/gates_policy_wiring.py"


def _repo_root_from_here() -> Path:
    here = Path(__file__).resolve()
    # Expected layout: <repo>/scripts/am_patch/gates_wiring_guard.py
    # parents[0] = <repo>/scripts/am_patch
    # parents[1] = <repo>/scripts
    # parents[2] = <repo>
    if len(here.parents) >= 3:
        return here.parents[2]
    raise RunnerError("PREFLIGHT", "INTERNAL", "unable to resolve repo root")


def _iter_py_files(am_patch_dir: Path) -> list[Path]:
    files = [p for p in am_patch_dir.rglob("*.py") if p.is_file()]
    return sorted(files, key=lambda p: str(p))


def _find_run_gates_calls(path: Path) -> list[int]:
    try:
        src = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise RunnerError(
            "PREFLIGHT",
            "INTERNAL",
            f"non-utf8 python source in scripts/am_patch: {path}: {e}",
        ) from e

    try:
        mod = ast.parse(src, filename=str(path))
    except SyntaxError as e:
        raise RunnerError(
            "PREFLIGHT",
            "INTERNAL",
            f"syntax error while scanning scripts/am_patch: {path}: {e}",
        ) from e

    out: list[int] = []
    for node in ast.walk(mod):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if (
            isinstance(fn, ast.Name)
            and fn.id == "run_gates"
            or isinstance(fn, ast.Attribute)
            and fn.attr == "run_gates"
        ):
            out.append(int(getattr(node, "lineno", 0) or 0))
    return out


def assert_single_run_gates_callsite() -> None:
    repo_root = _repo_root_from_here()
    am_patch_dir = repo_root / "scripts" / "am_patch"
    if not am_patch_dir.is_dir():
        raise RunnerError(
            "PREFLIGHT",
            "INTERNAL",
            f"missing scripts/am_patch directory at: {am_patch_dir}",
        )

    violations: list[tuple[str, int]] = []
    for py in _iter_py_files(am_patch_dir):
        rel = py.relative_to(repo_root).as_posix()
        lines = _find_run_gates_calls(py)
        if not lines:
            continue
        if rel == _ALLOWED_CALLSITE:
            continue
        for ln in lines:
            if ln > 0:
                violations.append((rel, ln))
            else:
                violations.append((rel, 0))

    if violations:
        violations.sort(key=lambda t: (t[0], t[1]))
        detail = "\n".join([f"- {p}:{ln}" for (p, ln) in violations])
        raise RunnerError(
            "PREFLIGHT",
            "INTERNAL",
            "run_gates call-sites must be centralized in scripts/am_patch/gates_policy_wiring.py\n"
            + detail,
        )
