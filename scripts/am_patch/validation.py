from __future__ import annotations

import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from am_patch.errors import RunnerError
from am_patch.gates import run_badguys, run_gates


@dataclass(frozen=True)
class GateSummary:
    ok: bool
    failing_stage: str | None = None
    failing_reason: str | None = None


def run_validation(
    *,
    logger: Any,
    repo_root: Path,
    cwd: Path,
    paths: Any,
    policy: Any,
    cli_mode: str,
    issue_id: int | None,
    decision_paths: list[str],
    progress: Any,
    run_badguys_gate: bool,
) -> GateSummary:
    run_gates(
        logger,
        cwd=cwd,
        repo_root=repo_root,
        run_all=policy.run_all_tests,
        compile_check=policy.compile_check,
        compile_targets=policy.compile_targets,
        compile_exclude=policy.compile_exclude,
        allow_fail=policy.gates_allow_fail,
        skip_ruff=policy.gates_skip_ruff,
        skip_js=policy.gates_skip_js,
        skip_pytest=policy.gates_skip_pytest,
        skip_mypy=policy.gates_skip_mypy,
        skip_docs=policy.gates_skip_docs,
        docs_include=policy.gate_docs_include,
        docs_exclude=policy.gate_docs_exclude,
        docs_required_files=policy.gate_docs_required_files,
        js_extensions=policy.gate_js_extensions,
        js_command=policy.gate_js_command,
        ruff_format=policy.ruff_format,
        ruff_autofix=policy.ruff_autofix,
        ruff_targets=policy.ruff_targets,
        pytest_targets=policy.pytest_targets,
        mypy_targets=policy.mypy_targets,
        gates_order=policy.gates_order,
        pytest_use_venv=policy.pytest_use_venv,
        decision_paths=decision_paths,
        progress=progress,
    )

    if run_badguys_gate and getattr(policy, "gate_badguys", False):
        _run_badguys(
            logger=logger,
            repo_root=repo_root,
            cwd=cwd,
            paths=paths,
            policy=policy,
            cli_mode=cli_mode,
            issue_id=issue_id,
            progress=progress,
            stage="badguys",
            decision_paths=decision_paths,
        )

    return GateSummary(ok=True)


def _run_badguys(
    *,
    logger: Any,
    repo_root: Path,
    cwd: Path,
    paths: Any,
    policy: Any,
    cli_mode: str,
    issue_id: int | None,
    progress: Any,
    stage: str,
    decision_paths: list[str],
) -> None:
    if decision_paths:
        logger.line(f"decision_paths_count={len(decision_paths)}")
    else:
        logger.line("decision_paths_count=0")

    raw_cmd = getattr(policy, "gate_badguys_command", None)
    command: list[str]
    if raw_cmd is None:
        command = ["badguys/badguys.py", "-q"]
    elif isinstance(raw_cmd, str):
        command = shlex.split(raw_cmd)
    else:
        command = [str(x) for x in raw_cmd]
    if not command:
        command = ["badguys/badguys.py", "-q"]

    cwd_mode = str(getattr(policy, "gate_badguys_cwd", "auto") or "auto").strip().lower()
    if cwd_mode not in ("auto", "workspace", "clone", "live"):
        cwd_mode = "auto"
    logger.line(f"gate_badguys_cwd={cwd_mode}")

    run_cwd = cwd
    isolated_repo: Path | None = None
    if cwd_mode == "clone" or (cwd_mode == "auto" and cwd.resolve() == repo_root.resolve()):
        tag = f"{cli_mode}_{issue_id or 'noissue'}"
        isolated_repo = paths.workspaces_dir / "_badguys_gate" / tag
        if isolated_repo.exists():
            shutil.rmtree(isolated_repo)
        isolated_repo.parent.mkdir(parents=True, exist_ok=True)
        src_repo = repo_root if cwd.resolve() == repo_root.resolve() else cwd
        logger.line(f"gate_badguys_repo=CLONE {src_repo} -> {isolated_repo}")
        r = logger.run_logged(
            ["git", "clone", "--no-hardlinks", str(src_repo), str(isolated_repo)],
            cwd=paths.workspaces_dir,
        )
        if r.returncode != 0:
            raise RunnerError("GATES", "GATES", "badguys clone failed")
        run_cwd = isolated_repo
    elif cwd_mode == "live":
        run_cwd = repo_root
        logger.line(f"gate_badguys_repo=LIVE {repo_root}")
    else:
        logger.line(f"gate_badguys_repo=CWD {cwd}")

    ok = False
    try:
        ok = run_badguys(logger, cwd=run_cwd, repo_root=repo_root, command=command)
    finally:
        if isolated_repo is not None:
            if ok:
                shutil.rmtree(isolated_repo, ignore_errors=True)
            else:
                logger.line(f"gate_badguys_repo_kept={isolated_repo}")
    progress(f"OK:{stage}" if ok else f"FAIL:{stage}")
    if not ok:
        raise RunnerError("GATES", "GATES", "gate failed: badguys")
