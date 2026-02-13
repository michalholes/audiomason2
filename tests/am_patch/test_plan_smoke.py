from __future__ import annotations

from pathlib import Path

from am_patch.model import CLIArgs
from am_patch.plan import build_plan, render_plan_summary


def test_cli_overrides_config(tmp_path: Path) -> None:
    cfg = tmp_path / "am_patch.toml"
    cfg.write_text(
        "verbosity = 'quiet'\n\n[test]\ntest_mode = true\n",
        encoding="utf-8",
    )

    repo_root = tmp_path / "repo"
    (repo_root / "scripts" / "am_patch").mkdir(parents=True)

    cli = CLIArgs(
        issue_id="800",
        commit_message=None,
        patch_input="patches/issue.zip",
        finalize_message=None,
        finalize_workspace=False,
        config_path=str(cfg),
        verbosity="debug",
        test_mode=False,
        update_workspace=False,
        unified_patch=False,
    )

    plan = build_plan(repo_root, cli)

    assert plan.parameters["verbosity"] == "debug"
    assert plan.parameters["test_mode"] is False


def test_plan_summary_is_deterministic(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "scripts" / "am_patch").mkdir(parents=True)

    cli = CLIArgs(
        issue_id="800",
        commit_message=None,
        patch_input="patches/issue.zip",
        finalize_message=None,
        finalize_workspace=None,
        config_path=None,
        verbosity="normal",
        test_mode=None,
        update_workspace=None,
        unified_patch=None,
    )

    p1 = build_plan(repo_root, cli)
    p2 = build_plan(repo_root, cli)

    assert render_plan_summary(p1) == render_plan_summary(p2)
