from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from .errors import RunnerError
from .log import Logger


def _norm_targets(targets: list[str], fallback: list[str]) -> list[str]:
    out: list[str] = []
    for t in targets:
        s = str(t).strip()
        if s and s not in out:
            out.append(s)
    return out or list(fallback)


def _venv_python(repo_root: Path) -> Path:
    # Do NOT .resolve() here: it may collapse the venv python symlink to /usr/bin/pythonX.Y
    # and lose venv site-packages.
    return repo_root / ".venv" / "bin" / "python"


def _cmd_py(module: str, *, python: str) -> list[str]:
    return [python, "-m", module]


def _norm_exclude_paths(exclude: list[str]) -> list[str]:
    out: list[str] = []
    for x in exclude:
        s = str(x).strip().replace("\\\\", "/")
        if s.startswith("./"):
            s = s[2:]
        s = s.strip("/")
        if s and s not in out:
            out.append(s)
    return out


def _compile_exclude_regex(exclude: list[str]) -> str | None:
    ex = _norm_exclude_paths(exclude)
    if not ex:
        return None
    parts = "|".join(re.escape(p) for p in ex)
    return rf"(^|/)({parts})(/|$)"


def _select_python_for_gate(
    *,
    repo_root: Path,
    gate: str,
    pytest_use_venv: bool,
) -> str:
    if gate == "pytest" and pytest_use_venv:
        vpy = _venv_python(repo_root)
        if not vpy.exists():
            raise RunnerError(
                "GATES", "PYTEST_VENV", f"pytest_use_venv=true but venv python not found: {vpy}"
            )
        return str(vpy)
    return sys.executable


def run_ruff(
    logger: Logger,
    cwd: Path,
    *,
    repo_root: Path,
    ruff_format: bool,
    autofix: bool,
    targets: list[str],
) -> bool:
    targets = _norm_targets(targets, ["src", "tests"])
    py = _select_python_for_gate(repo_root=repo_root, gate="ruff", pytest_use_venv=False)

    if ruff_format:
        logger.section("GATE: RUFF FORMAT")
        rfmt = logger.run_logged(_cmd_py("ruff", python=py) + ["format", *targets], cwd=cwd)
        if rfmt.returncode != 0:
            return False

    logger.section("GATE: RUFF (initial)")
    r = logger.run_logged(_cmd_py("ruff", python=py) + ["check", *targets], cwd=cwd)
    if r.returncode == 0:
        return True
    if not autofix:
        return False

    logger.section("GATE: RUFF (fix)")
    _ = logger.run_logged(_cmd_py("ruff", python=py) + ["check", *targets, "--fix"], cwd=cwd)

    logger.section("GATE: RUFF (final)")
    r2 = logger.run_logged(_cmd_py("ruff", python=py) + ["check", *targets], cwd=cwd)
    return r2.returncode == 0


def run_pytest(
    logger: Logger, cwd: Path, *, repo_root: Path, pytest_use_venv: bool, targets: list[str]
) -> bool:
    targets = _norm_targets(targets, ["tests"])

    # IMPORTANT: pytest may need dependencies that exist only inside repo_root/.venv.
    # When pytest_use_venv=true, always use repo_root/.venv/bin/python explicitly.
    if pytest_use_venv:
        vpy = _venv_python(repo_root)
        if not vpy.exists():
            raise RunnerError(
                "GATES", "PYTEST_VENV", f"pytest_use_venv=true but venv python not found: {vpy}"
            )
        py = str(vpy)
    else:
        py = sys.executable

    logger.section("GATE: PYTEST")
    logger.line(f"pytest_use_venv={pytest_use_venv}")
    logger.line(f"sys_executable={sys.executable}")
    logger.line(f"pytest_python={py}")
    env = None
    if pytest_use_venv:
        # Ensure subprocesses spawned by tests can resolve `audiomason`.
        # This is done by prefixing PATH with the venv bin dir.
        env = dict(os.environ)
        venv_root = repo_root / ".venv"
        venv_bin = venv_root / "bin"
        old_path = env.get("PATH", "")
        env["PATH"] = f"{venv_bin}:{old_path}" if old_path else str(venv_bin)
        env["VIRTUAL_ENV"] = str(venv_root)
    r = logger.run_logged(_cmd_py("pytest", python=py) + ["-q", *targets], cwd=cwd, env=env)
    return r.returncode == 0


def run_mypy(logger: Logger, cwd: Path, *, repo_root: Path, targets: list[str]) -> bool:
    targets = _norm_targets(targets, ["src"])
    py = _select_python_for_gate(repo_root=repo_root, gate="mypy", pytest_use_venv=False)
    logger.section("GATE: MYPY")
    r = logger.run_logged(_cmd_py("mypy", python=py) + [*targets], cwd=cwd)
    return r.returncode == 0


def run_compile_check(
    logger: Logger,
    cwd: Path,
    *,
    repo_root: Path,
    targets: list[str],
    exclude: list[str],
) -> bool:
    """Compile Python sources to catch syntax errors early."""
    logger.section("GATE: compile")
    py = sys.executable
    logger.line(f"compile_python={py}")
    targets = _norm_targets(targets, ["."])
    exclude = _norm_exclude_paths(exclude)
    logger.line(f"compile_targets={targets}")
    logger.line(f"compile_exclude={exclude}")
    cmd: list[str] = [py, "-m", "compileall", "-q"]
    rx = _compile_exclude_regex(exclude)
    if rx:
        logger.line(f"compile_exclude_regex={rx}")
        cmd += ["-x", rx]
    cmd += targets
    r = logger.run_logged(cmd, cwd=cwd)
    return r.returncode == 0


def _norm_gate_name(s: str) -> str:
    return str(s).strip().lower()


def _norm_gates_order(order: list[str] | None) -> list[str]:
    if not order:
        return []
    allowed = {"compile", "ruff", "pytest", "mypy"}
    out: list[str] = []
    for item in order:
        name = _norm_gate_name(item)
        if name in allowed and name not in out:
            out.append(name)
    return out


def run_gates(
    logger: Logger,
    cwd: Path,
    *,
    repo_root: Path,
    run_all: bool,
    compile_check: bool,
    compile_targets: list[str],
    compile_exclude: list[str],
    allow_fail: bool,
    skip_ruff: bool,
    skip_pytest: bool,
    skip_mypy: bool,
    ruff_format: bool,
    ruff_autofix: bool,
    ruff_targets: list[str],
    pytest_targets: list[str],
    mypy_targets: list[str],
    gates_order: list[str] | None,
    pytest_use_venv: bool,
) -> None:
    failures: list[str] = []
    skipped: list[str] = []

    order = _norm_gates_order(gates_order)
    if not order:
        logger.section("GATES: SKIPPED (gates_order empty)")
        return

    def _run_gate(name: str) -> bool:
        if name == "compile":
            if not compile_check:
                skipped.append("compile")
                logger.line("gate_compile=SKIP (disabled_by_policy)")
                return True
            return run_compile_check(
                logger,
                cwd=cwd,
                repo_root=repo_root,
                targets=compile_targets,
                exclude=compile_exclude,
            )

        if name == "ruff":
            if skip_ruff:
                skipped.append("ruff")
                logger.line("gate_ruff=SKIP (skipped_by_user)")
                return True
            return run_ruff(
                logger,
                cwd,
                repo_root=repo_root,
                ruff_format=ruff_format,
                autofix=ruff_autofix,
                targets=ruff_targets,
            )

        if name == "pytest":
            if skip_pytest:
                skipped.append("pytest")
                logger.line("gate_pytest=SKIP (skipped_by_user)")
                return True
            return run_pytest(
                logger,
                cwd,
                repo_root=repo_root,
                pytest_use_venv=pytest_use_venv,
                targets=pytest_targets,
            )

        if name == "mypy":
            if skip_mypy:
                skipped.append("mypy")
                logger.line("gate_mypy=SKIP (skipped_by_user)")
                return True
            return run_mypy(logger, cwd, repo_root=repo_root, targets=mypy_targets)

        return True

    for gate in ("compile", "ruff", "pytest", "mypy"):
        if gate not in order:
            skipped.append(gate)
            logger.line(f"gate_{gate}=SKIP (not in gates_order)")

    for gate in order:
        ok = _run_gate(gate)
        if not ok:
            failures.append(gate)
            if not run_all:
                if allow_fail:
                    break
                raise RunnerError("GATES", "GATES", f"gate failed: {gate}")

    if failures and not allow_fail:
        raise RunnerError("GATES", "GATES", "gates failed: " + ", ".join(failures))

    if failures and allow_fail:
        logger.line("gates_failed_allowed=true")
        logger.line("gates_failed=" + ",".join(failures))
