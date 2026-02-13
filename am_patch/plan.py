from __future__ import annotations

from pathlib import Path

from .config import load_shadow_config
from .model import CLIArgs, ExecutionPlan, Phase


def build_plan(repo_root: Path, cli: CLIArgs) -> ExecutionPlan:
    """Build a deterministic ExecutionPlan for the root runner."""

    cfg, cfg_path, sources = load_shadow_config(repo_root, cli)

    mode = "workspace"
    if cli.finalize_message:
        mode = "finalize"
    elif cli.finalize_workspace:
        mode = "finalize_workspace"

    effective_test_mode = cfg.test_mode

    phases: list[Phase] = [Phase.PREFLIGHT]

    # Workspace is always created for workspace/finalize-workspace, never for finalize-live.
    if mode in {"workspace", "finalize_workspace"}:
        phases.append(Phase.WORKSPACE)
        phases.append(Phase.PATCH)
        phases.append(Phase.GATES_WORKSPACE)

        if mode == "finalize_workspace" and not effective_test_mode:
            phases.append(Phase.PROMOTE)
            phases.append(Phase.GATES_LIVE)
            phases.append(Phase.ARCHIVE)
            phases.append(Phase.COMMIT)
            phases.append(Phase.PUSH)

        phases.append(Phase.CLEANUP)

    else:  # finalize (live)
        phases.append(Phase.PATCH)
        phases.append(Phase.GATES_LIVE)
        if not effective_test_mode:
            phases.append(Phase.ARCHIVE)
            phases.append(Phase.COMMIT)
            phases.append(Phase.PUSH)

    params: dict[str, object] = {
        "issue_id": cli.issue_id,
        "commit_message": cli.finalize_message or cli.commit_message,
        "verbosity": cfg.verbosity,
        "test_mode": effective_test_mode,
        "update_workspace": bool(cli.update_workspace) if cli.update_workspace is not None else False,
        "unified_patch": bool(cli.unified_patch) if cli.unified_patch is not None else False,
        "patch_input": cli.patch_input,
    }

    return ExecutionPlan(
        mode=mode,
        repo_root=repo_root,
        config_path=cfg_path,
        config_sources=sources,
        phases=tuple(phases),
        parameters=params,
    )


def render_plan_summary(plan: ExecutionPlan) -> str:
    lines: list[str] = []
    lines.append("am_patch (root runner) PLAN")
    lines.append(f"mode={plan.mode}")
    lines.append(f"repo_root={plan.repo_root}")
    lines.append(f"config_path={plan.config_path}")
    lines.append(f"config_sources={','.join(plan.config_sources)}")
    lines.append("phases=" + ",".join(p.value for p in plan.phases))
    lines.append("parameters:")
    for k in sorted(plan.parameters.keys()):
        lines.append(f"  - {k}={plan.parameters[k]}")
    return "\n".join(lines) + "\n"
