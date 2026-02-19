from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable
from pathlib import Path

from .errors import RunnerError
from .log import Logger
from .monolith_gate import run_monolith_gate


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


def _infer_venv_root(python_exe: str) -> Path | None:
    p = Path(python_exe)
    # Detect the common layout: <repo>/.venv/bin/python
    if p.name == "python" and p.parent.name == "bin" and p.parent.parent.name == ".venv":
        return p.parent.parent
    return None


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


def _norm_rel_path(p: str) -> str:
    s = str(p).strip().replace("\\", "/")
    if s.startswith("./"):
        s = s[2:]
    s = s.strip("/")
    return s


def _norm_rel_paths(paths: list[str]) -> list[str]:
    out: list[str] = []
    for p in paths:
        s = _norm_rel_path(p)
        if s and s not in out:
            out.append(s)
    return out


def _path_has_prefix(path: str, prefix: str) -> bool:
    # Directory-prefix match with boundary (src matches src/a.py but not src2/a.py).
    if not prefix:
        return False
    if path == prefix:
        return True
    return path.startswith(prefix + "/")


def _docs_gate_is_watched(
    decision_paths: list[str],
    *,
    include: list[str],
    exclude: list[str],
) -> tuple[bool, str | None]:
    inc = _norm_rel_paths(include)
    exc = _norm_rel_paths(exclude)
    paths = _norm_rel_paths(decision_paths)

    for p in paths:
        if any(_path_has_prefix(p, x) for x in exc):
            continue
        if any(_path_has_prefix(p, i) for i in inc):
            return True, p
    return False, None


def check_docs_gate(
    decision_paths: list[str],
    *,
    include: list[str],
    exclude: list[str],
    required_files: list[str],
) -> tuple[bool, list[str], str | None]:
    """Return (ok, missing_required, trigger_path).

    The gate triggers only if at least one changed path matches include and does not match exclude.
    If triggered, all required_files must be present in decision_paths to pass.
    """
    triggered, trigger_path = _docs_gate_is_watched(
        decision_paths, include=include, exclude=exclude
    )
    if not triggered:
        return True, [], None

    paths_set = set(_norm_rel_paths(decision_paths))
    req = _norm_rel_paths(required_files)
    missing = [r for r in req if r not in paths_set]
    return len(missing) == 0, missing, trigger_path


def _norm_js_extensions(exts: list[str]) -> list[str]:
    out: list[str] = []
    for e in exts:
        s = str(e).strip().lower()
        if not s:
            continue
        if not s.startswith("."):
            s = "." + s
        if s not in out:
            out.append(s)
    return out


def check_js_gate(
    decision_paths: list[str],
    *,
    extensions: list[str],
) -> tuple[bool, list[str]]:
    """Return (triggered, js_paths).

    The gate triggers only if at least one changed path ends with one of the configured extensions.
    Returned js_paths are normalized repo-relative paths (forward slashes, no leading ./).
    """
    exts = _norm_js_extensions(extensions)
    if not exts:
        return False, []

    paths = _norm_rel_paths(decision_paths)
    js_paths: list[str] = []
    for p in paths:
        pl = p.lower()
        if any(pl.endswith(e) for e in exts):
            js_paths.append(p)

    if not js_paths:
        return False, []
    js_paths.sort()
    return True, js_paths


def run_js_syntax_gate(
    logger: Logger,
    cwd: Path,
    *,
    decision_paths: list[str],
    extensions: list[str],
    command: list[str],
) -> bool:
    """Run JS syntax validation via an external command (default: node --check).

    The gate is a no-op (SKIP) when no JS files are touched.
    """
    triggered, js_paths = check_js_gate(decision_paths, extensions=extensions)
    if not triggered:
        logger.warning_core("gate_js=SKIP (no_js_touched)")
        return True

    cmd0 = [str(x) for x in command if str(x).strip()]
    if not cmd0:
        raise RunnerError("GATES", "JS_CMD", "gate_js_command must be non-empty")

    logger.section("GATE: JS SYNTAX")
    logger.line("gate_js_extensions=" + ",".join(_norm_js_extensions(extensions)))
    logger.line("gate_js_cmd=" + " ".join(cmd0))

    for rel in js_paths:
        logger.line("gate_js_file=" + rel)
        r = logger.run_logged([*cmd0, rel], cwd=cwd)
        if r.returncode != 0:
            return False
    return True


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

    # IMPORTANT: pytest may need dependencies that exist only inside a venv.
    # Preferred: use repo_root/.venv/bin/python when it exists.
    # Fallback: if the workspace/clone repo has no .venv, but this runner itself is
    # already executing from a venv (sys.executable), use sys.executable.
    venv_root: Path | None = None
    if pytest_use_venv:
        vpy = _venv_python(repo_root)
        if vpy.exists():
            py = str(vpy)
            venv_root = repo_root / ".venv"
        else:
            venv_root = _infer_venv_root(sys.executable)
            if venv_root is None or not Path(sys.executable).exists():
                msg = (
                    f"pytest_use_venv=true but venv python not found: {vpy} "
                    "(and no usable venv in sys.executable)"
                )
                raise RunnerError(
                    "GATES",
                    "PYTEST_VENV",
                    msg,
                )
            py = sys.executable
    else:
        py = sys.executable

    logger.section("GATE: PYTEST")
    logger.line(f"pytest_use_venv={pytest_use_venv}")
    logger.line(f"sys_executable={sys.executable}")
    logger.line(f"pytest_python={py}")
    env = dict(os.environ)
    env["AM_PATCH_PYTEST_GATE"] = "1"
    if pytest_use_venv and venv_root is not None:
        # Ensure subprocesses spawned by tests can resolve `audiomason`.
        # This is done by prefixing PATH with the venv bin dir.
        venv_bin = venv_root / "bin"
        old_path = env.get("PATH", "")
        env["PATH"] = f"{venv_bin}:{old_path}" if old_path else str(venv_bin)
        env["VIRTUAL_ENV"] = str(venv_root)
    r = logger.run_logged(_cmd_py("pytest", python=py) + ["-q", *targets], cwd=cwd, env=env)
    return r.returncode == 0


def run_badguys(
    logger: Logger,
    cwd: Path,
    *,
    repo_root: Path,
    command: list[str],
) -> bool:
    logger.section("GATE: BADGUYS")
    logger.line(f"badguys_python={sys.executable}")
    env = dict(os.environ)
    env["AM_PATCH_BADGUYS_GATE"] = "1"
    # Ensure BadGuys uses the same Python as the runner for nested am_patch invocations.
    env["AM_PATCH_BADGUYS_RUNNER_PYTHON"] = sys.executable
    # If we are running from a venv, propagate PATH/VIRTUAL_ENV so nested processes
    # can find the same toolchain even inside workspace/clone repos.
    venv_root = _infer_venv_root(sys.executable)
    if venv_root is not None:
        venv_bin = venv_root / "bin"
        old_path = env.get("PATH", "")
        env["PATH"] = f"{venv_bin}:{old_path}" if old_path else str(venv_bin)
        env["VIRTUAL_ENV"] = str(venv_root)
    logger.line(f"badguys_cmd={command}")
    cmd = [sys.executable, "-u", *command]
    r = logger.run_logged(cmd, cwd=cwd, env=env)
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
    allowed = {"compile", "js", "ruff", "pytest", "mypy", "docs", "monolith"}
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
    skip_js: bool,
    skip_pytest: bool,
    skip_mypy: bool,
    skip_docs: bool,
    skip_monolith: bool,
    gate_monolith_enabled: bool,
    gate_monolith_mode: str,
    gate_monolith_scan_scope: str,
    gate_monolith_compute_fanin: bool,
    gate_monolith_on_parse_error: str,
    gate_monolith_areas: list[dict[str, str]],
    gate_monolith_large_loc: int,
    gate_monolith_huge_loc: int,
    gate_monolith_large_allow_loc_increase: int,
    gate_monolith_huge_allow_loc_increase: int,
    gate_monolith_large_allow_exports_delta: int,
    gate_monolith_huge_allow_exports_delta: int,
    gate_monolith_large_allow_imports_delta: int,
    gate_monolith_huge_allow_imports_delta: int,
    gate_monolith_new_file_max_loc: int,
    gate_monolith_new_file_max_exports: int,
    gate_monolith_new_file_max_imports: int,
    gate_monolith_hub_fanin_delta: int,
    gate_monolith_hub_fanout_delta: int,
    gate_monolith_hub_exports_delta_min: int,
    gate_monolith_hub_loc_delta_min: int,
    gate_monolith_crossarea_min_distinct_areas: int,
    gate_monolith_catchall_basenames: list[str],
    gate_monolith_catchall_dirs: list[str],
    gate_monolith_catchall_allowlist: list[str],
    docs_include: list[str],
    docs_exclude: list[str],
    docs_required_files: list[str],
    js_extensions: list[str],
    js_command: list[str],
    ruff_format: bool,
    ruff_autofix: bool,
    ruff_targets: list[str],
    pytest_targets: list[str],
    mypy_targets: list[str],
    gates_order: list[str] | None,
    pytest_use_venv: bool,
    decision_paths: list[str],
    progress: Callable[[str], None] | None = None,
) -> None:
    failures: list[str] = []
    skipped: list[str] = []

    order = _norm_gates_order(gates_order)
    if not order:
        logger.section("GATES: SKIPPED (gates_order empty)")
        logger.warning_core("GATES: SKIPPED (gates_order empty)")
        return

    def _run_gate(name: str) -> bool:
        if name == "compile":
            if not compile_check:
                skipped.append("compile")
                logger.warning_core("gate_compile=SKIP (disabled_by_policy)")
                return True
            return run_compile_check(
                logger,
                cwd=cwd,
                repo_root=repo_root,
                targets=compile_targets,
                exclude=compile_exclude,
            )

        if name == "js":
            if skip_js:
                skipped.append("js")
                logger.warning_core("gate_js=SKIP (skipped_by_user)")
                return True
            return run_js_syntax_gate(
                logger,
                cwd=cwd,
                decision_paths=decision_paths,
                extensions=js_extensions,
                command=js_command,
            )

        if name == "ruff":
            if skip_ruff:
                skipped.append("ruff")
                logger.warning_core("gate_ruff=SKIP (skipped_by_user)")
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
                logger.warning_core("gate_pytest=SKIP (skipped_by_user)")
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
                logger.warning_core("gate_mypy=SKIP (skipped_by_user)")
                return True
            return run_mypy(logger, cwd, repo_root=repo_root, targets=mypy_targets)

        if name == "monolith":
            if skip_monolith:
                skipped.append("monolith")
                logger.warning_core("gate_monolith=SKIP (skipped_by_user)")
                return True
            if not gate_monolith_enabled:
                skipped.append("monolith")
                logger.warning_core("gate_monolith=SKIP (disabled_by_policy)")
                return True
            return run_monolith_gate(
                logger,
                cwd,
                repo_root=repo_root,
                decision_paths=decision_paths,
                gate_monolith_mode=gate_monolith_mode,
                gate_monolith_scan_scope=gate_monolith_scan_scope,
                gate_monolith_compute_fanin=gate_monolith_compute_fanin,
                gate_monolith_on_parse_error=gate_monolith_on_parse_error,
                gate_monolith_areas=gate_monolith_areas,
                gate_monolith_large_loc=gate_monolith_large_loc,
                gate_monolith_huge_loc=gate_monolith_huge_loc,
                gate_monolith_large_allow_loc_increase=gate_monolith_large_allow_loc_increase,
                gate_monolith_huge_allow_loc_increase=gate_monolith_huge_allow_loc_increase,
                gate_monolith_large_allow_exports_delta=gate_monolith_large_allow_exports_delta,
                gate_monolith_huge_allow_exports_delta=gate_monolith_huge_allow_exports_delta,
                gate_monolith_large_allow_imports_delta=gate_monolith_large_allow_imports_delta,
                gate_monolith_huge_allow_imports_delta=gate_monolith_huge_allow_imports_delta,
                gate_monolith_new_file_max_loc=gate_monolith_new_file_max_loc,
                gate_monolith_new_file_max_exports=gate_monolith_new_file_max_exports,
                gate_monolith_new_file_max_imports=gate_monolith_new_file_max_imports,
                gate_monolith_hub_fanin_delta=gate_monolith_hub_fanin_delta,
                gate_monolith_hub_fanout_delta=gate_monolith_hub_fanout_delta,
                gate_monolith_hub_exports_delta_min=gate_monolith_hub_exports_delta_min,
                gate_monolith_hub_loc_delta_min=gate_monolith_hub_loc_delta_min,
                gate_monolith_crossarea_min_distinct_areas=gate_monolith_crossarea_min_distinct_areas,
                gate_monolith_catchall_basenames=gate_monolith_catchall_basenames,
                gate_monolith_catchall_dirs=gate_monolith_catchall_dirs,
                gate_monolith_catchall_allowlist=gate_monolith_catchall_allowlist,
            )

        if name == "docs":
            if skip_docs:
                skipped.append("docs")
                logger.warning_core("gate_docs=SKIP (skipped_by_user)")
                return True
            ok, missing, trigger = check_docs_gate(
                decision_paths,
                include=docs_include,
                exclude=docs_exclude,
                required_files=docs_required_files,
            )
            if ok:
                logger.line("gate_docs=OK")
                return True
            trig = trigger or "unknown"
            logger.error_core("gate_docs=FAIL")
            logger.error_core("gate_docs_trigger=" + trig)
            logger.error_core("gate_docs_missing=" + ",".join(missing))
            return False

        return True

    for gate in ("compile", "js", "ruff", "pytest", "mypy", "docs", "monolith"):
        if gate not in order:
            skipped.append(gate)
            logger.warning_core(f"gate_{gate}=SKIP (not in gates_order)")

    for gate in order:
        stage = f"GATE_{gate.upper()}"
        if progress is not None:
            progress(f"DO:{stage}")
        ok = _run_gate(gate)
        if progress is not None:
            progress(f"OK:{stage}" if ok else f"FAIL:{stage}")
        if not ok:
            failures.append(gate)
            if not run_all:
                if allow_fail:
                    break
                raise RunnerError("GATES", "GATES", f"gate failed: {gate}")

    if failures and not allow_fail:
        raise RunnerError("GATES", "GATES", "gates failed: " + ", ".join(failures))

    if failures and allow_fail:
        logger.warning_core("gates_failed_allowed=true")
        logger.warning_core("gates_failed=" + ",".join(failures))
