from __future__ import annotations

from pathlib import Path

from .archive import create_archives
from .deps import Deps, default_deps
from .gates import GateSpec, run_gate_specs
from .git_ops import git_commit, git_push
from .logging import RunLogger, default_log_path
from .model import ExecutionPlan, Phase, PhaseFailed, PhaseResult, RunResult, RunnerError
from .patch_exec import apply_patch
from .promote import promote_from_workspace
from .workspace import cleanup_workspace, create_workspace


def _default_gate_specs() -> tuple[GateSpec, ...]:
    return (
        GateSpec(name="compileall", argv=("python", "-m", "compileall", "am_patch", "tests")),
        GateSpec(name="pytest_am_patch", argv=("pytest", "-q", "tests/am_patch")),
    )


def execute_plan(plan: ExecutionPlan, deps: Deps | None = None) -> RunResult:
    deps = deps or default_deps()

    issue_id = str(plan.parameters.get("issue_id") or "")
    patch_input_raw = plan.parameters.get("patch_input")
    patch_input = Path(str(patch_input_raw)) if patch_input_raw else None
    if patch_input is not None and not patch_input.is_absolute():
        patch_input = plan.repo_root / patch_input

    commit_message = str(plan.parameters.get("commit_message") or "")
    test_mode = bool(plan.parameters.get("test_mode") or False)
    update_ws = bool(plan.parameters.get("update_workspace") or False)

    log_path = default_log_path(plan.repo_root, issue_id or None)
    logger = RunLogger(log_path)
    phase_results: list[PhaseResult] = []

    deps.events.emit(f"run_start mode={plan.mode} test_mode={test_mode}")
    logger.write_line(f"RUN mode={plan.mode} test_mode={test_mode}")

    ws_repo: Path | None = None
    changed_paths: tuple[str, ...] = ()

    def _ok(phase: Phase, detail: str = "") -> None:
        phase_results.append(PhaseResult(phase=phase, ok=True, detail=detail))

    def _fail(phase: Phase, exc: Exception) -> None:
        msg = str(exc)
        phase_results.append(PhaseResult(phase=phase, ok=False, detail=msg))
        raise PhaseFailed(phase, msg)

    exit_code = 0
    try:
        for phase in plan.phases:
            deps.events.emit(f"phase_start:{phase.value}")
            logger.phase_start(phase.value)

            try:
                if phase == Phase.PREFLIGHT:
                    if not issue_id:
                        raise RunnerError("missing issue_id")
                    if patch_input is None:
                        raise RunnerError("missing patch_input")
                    if not patch_input.exists():
                        raise RunnerError(f"patch_input not found: {patch_input}")
                    _ok(phase)

                elif phase == Phase.WORKSPACE:
                    ws_repo = create_workspace(plan.repo_root, issue_id, deps, update=update_ws).path
                    _ok(phase, detail=str(ws_repo))

                elif phase == Phase.PATCH:
                    if patch_input is None:
                        raise RunnerError("missing patch_input")
                    if plan.mode == "finalize":
                        target = plan.repo_root
                    else:
                        if ws_repo is None:
                            raise RunnerError("workspace not created")
                        target = ws_repo
                    changed_paths = apply_patch(target, patch_input, deps).changed_paths
                    _ok(phase, detail=",".join(changed_paths))

                elif phase in {Phase.GATES_WORKSPACE, Phase.GATES_LIVE}:
                    target = plan.repo_root if phase == Phase.GATES_LIVE else ws_repo
                    if target is None:
                        raise RunnerError("missing target for gates")
                    run_gate_specs(deps, target, _default_gate_specs())
                    _ok(phase)

                elif phase == Phase.PROMOTE:
                    if test_mode:
                        _ok(phase, detail="skipped_test_mode")
                    else:
                        if ws_repo is None:
                            raise RunnerError("workspace not created")
                        promote_from_workspace(ws_repo, plan.repo_root, deps, changed_paths)
                        _ok(phase)

                elif phase == Phase.ARCHIVE:
                    if test_mode:
                        _ok(phase, detail="skipped_test_mode")
                    else:
                        ar = create_archives(plan.repo_root, issue_id or None, include_success=True)
                        _ok(phase, detail=str(ar.patched_zip))

                elif phase == Phase.COMMIT:
                    if test_mode:
                        _ok(phase, detail="skipped_test_mode")
                    else:
                        if not commit_message:
                            raise RunnerError("missing commit message")
                        git_commit(deps, plan.repo_root, commit_message)
                        _ok(phase)

                elif phase == Phase.PUSH:
                    if test_mode:
                        _ok(phase, detail="skipped_test_mode")
                    else:
                        git_push(deps, plan.repo_root)
                        _ok(phase)

                elif phase == Phase.CLEANUP:
                    if ws_repo is not None:
                        cleanup_workspace(ws_repo, deps)
                        ws_repo = None
                    _ok(phase)

                else:
                    raise RunnerError(f"unknown phase: {phase}")

            except Exception as e:  # noqa: BLE001
                logger.phase_end(phase.value, ok=False, detail=str(e))
                deps.events.emit(f"phase_end:{phase.value}:ok=0")
                _fail(phase, e)

            logger.phase_end(phase.value, ok=True)
            deps.events.emit(f"phase_end:{phase.value}:ok=1")

    except PhaseFailed:
        exit_code = 2
    except Exception as e:  # noqa: BLE001
        logger.write_line(f"FATAL {e}")
        exit_code = 2
    finally:
        # Enforce test-mode cleanup policy.
        if test_mode and ws_repo is not None:
            try:
                cleanup_workspace(ws_repo, deps)
            except Exception:
                pass

    ok = exit_code == 0 and all(r.ok for r in phase_results)
    deps.events.emit(f"run_end ok={ok}")
    logger.write_line(f"RESULT ok={ok}")
    return RunResult(
        ok=ok,
        exit_code=exit_code,
        phase_results=tuple(phase_results),
        events=tuple(getattr(deps.events, "events", [])),
        log_path=log_path,
    )
