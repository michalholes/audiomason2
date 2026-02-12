from __future__ import annotations

from pathlib import Path

from .config import load_shadow_config
from .model import CLIArgs, ExecutionPlan, Phase


def build_plan(repo_root: Path, cli: CLIArgs) -> ExecutionPlan:
    """Build a deterministic ExecutionPlan.

    Planning-only: no patch application, no gates execution, no git operations.
    """

    cfg, cfg_path, sources = load_shadow_config(repo_root, cli)

    mode = "workspace"
    if cli.finalize_message:
        mode = "finalize"
    elif cli.finalize_workspace_issue_id:
        mode = "finalize_workspace"

    # test_mode can be expressed either by CLI flag or config.
    effective_test_mode = cfg.test_mode

    phases: list[Phase]
    if mode == "workspace":
        phases = [Phase.PREFLIGHT, Phase.PATCH, Phase.GATES]
        if effective_test_mode:
            phases.append(Phase.CLEANUP)
        else:
            phases.extend([Phase.PROMOTE, Phase.COMMIT, Phase.PUSH, Phase.ARCHIVE])
    else:
        phases = [Phase.PREFLIGHT, Phase.GATES]
        if effective_test_mode:
            phases.append(Phase.CLEANUP)
        else:
            phases.extend([Phase.PROMOTE, Phase.COMMIT, Phase.PUSH, Phase.ARCHIVE])

    params: dict[str, object] = {
        "issue_id": cli.finalize_workspace_issue_id or cli.issue_id,
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
    """Render plan summary deterministically."""

    lines: list[str] = []
    lines.append("am_patch (shadow runner) PLAN")
    lines.append(f"mode={plan.mode}")
    lines.append(f"repo_root={plan.repo_root}")
    lines.append(f"config_path={plan.config_path}")
    lines.append(f"config_sources={','.join(plan.config_sources)}")
    lines.append("phases=" + ",".join(p.value for p in plan.phases))

    # Sorted keys for stable output.
    lines.append("parameters:")
    for k in sorted(plan.parameters.keys()):
        lines.append(f"  - {k}={plan.parameters[k]}")

    return "\n".join(lines) + "\n"
