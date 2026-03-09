from pathlib import Path

from badguys.bdg_executor import execute_bdg_step
from badguys.bdg_loader import BdgAsset, BdgStep, BdgTest
from badguys.bdg_materializer import materialize_assets
from badguys.bdg_recipe import step_recipe, subject_relpaths
from badguys.bdg_subst import SubstCtx


def _write_alt_config(repo_root: Path) -> Path:
    cfg_dir = repo_root / "badguys"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    path = cfg_dir / "alt.toml"
    path.write_text(
        """
[suite]
issue_id = "777"
runner_cmd = ["python3", "scripts/am_patch.py"]
runner_verbosity = "quiet"
console_verbosity = "quiet"
log_verbosity = "quiet"
patches_dir = "patches"
logs_dir = "patches/badguys_logs_alt"
commit_limit = 0

[lock]
path = "patches/badguys.lock"
ttl_seconds = 3600
on_conflict = "fail"

[guard]
require_guard_test = false
guard_test_name = "test_000_test_mode_smoke"
abort_on_guard_fail = true

[filters]
include = []
exclude = []

[runner]
full_runner_tests = []

[subjects.tests.test_cfg.subject_a]
relpath = "docs/alt_subject.txt"

[recipes.tests.test_cfg.steps.0]
runner_verbosity = "debug"

[recipes.tests.test_cfg.steps.1]
commit_limit = 7
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return path


def test_recipe_helpers_use_selected_config_path(tmp_path: Path) -> None:
    repo_root = tmp_path
    alt_path = _write_alt_config(repo_root)

    subjects = subject_relpaths(
        repo_root=repo_root,
        config_path=alt_path.relative_to(repo_root),
        test_id="test_cfg",
    )
    recipe = step_recipe(
        repo_root=repo_root,
        config_path=alt_path.relative_to(repo_root),
        test_id="test_cfg",
        step_index=0,
    )

    assert subjects == {"subject_a": "docs/alt_subject.txt"}
    assert recipe == {"runner_verbosity": "debug"}


def test_build_cfg_appends_recipe_commit_limit_override(tmp_path: Path) -> None:
    repo_root = tmp_path
    alt_path = _write_alt_config(repo_root)
    bdg = BdgTest(
        test_id="test_cfg",
        makes_commit=False,
        is_guard=False,
        assets={
            "cfg": BdgAsset(
                asset_id="cfg",
                kind="toml_text",
                content='[suite]\nrunner_verbosity = "quiet"\ncommit_limit = 0\n',
                entries=[],
            )
        },
        steps=[BdgStep(op="BUILD_CFG", params={"input_asset": "cfg"})],
    )
    subst = SubstCtx(issue_id="777", now_stamp="20260307_150000")
    mats = materialize_assets(
        repo_root=repo_root,
        config_path=alt_path.relative_to(repo_root),
        subst=subst,
        bdg=bdg,
    )

    result = execute_bdg_step(
        repo_root=repo_root,
        config_path=alt_path.relative_to(repo_root),
        cfg_runner_cmd=["python3", "scripts/am_patch.py", "--verbosity=quiet"],
        subst=subst,
        full_runner_tests=set(),
        step=bdg.steps[0],
        mats=mats,
        test_id=bdg.test_id,
        step_index=1,
        step_runner_cfg={
            "artifacts_dir": repo_root / "patches" / "artifacts",
            "console_verbosity": "quiet",
            "copy_runner_log": False,
            "patches_dir": repo_root / "patches",
            "write_subprocess_stdio": False,
        },
    )

    assert result.rc == 0
    assert result.value is not None
    assert "--commit-limit=7" in result.value


def test_build_cfg_uses_recipe_from_selected_config_path(tmp_path: Path) -> None:
    repo_root = tmp_path
    alt_path = _write_alt_config(repo_root)
    bdg = BdgTest(
        test_id="test_cfg",
        makes_commit=False,
        is_guard=False,
        assets={
            "cfg": BdgAsset(
                asset_id="cfg",
                kind="toml_text",
                content='[suite]\nrunner_verbosity = "quiet"\n',
                entries=[],
            )
        },
        steps=[BdgStep(op="BUILD_CFG", params={"input_asset": "cfg"})],
    )
    subst = SubstCtx(issue_id="777", now_stamp="20260307_150000")
    mats = materialize_assets(
        repo_root=repo_root,
        config_path=alt_path.relative_to(repo_root),
        subst=subst,
        bdg=bdg,
    )

    result = execute_bdg_step(
        repo_root=repo_root,
        config_path=alt_path.relative_to(repo_root),
        cfg_runner_cmd=["python3", "scripts/am_patch.py", "--verbosity=quiet"],
        subst=subst,
        full_runner_tests=set(),
        step=bdg.steps[0],
        mats=mats,
        test_id=bdg.test_id,
        step_index=0,
        step_runner_cfg={
            "artifacts_dir": repo_root / "patches" / "artifacts",
            "console_verbosity": "quiet",
            "copy_runner_log": False,
            "patches_dir": repo_root / "patches",
            "write_subprocess_stdio": False,
        },
    )

    assert result.rc == 0
    assert result.value is not None
    assert "--verbosity=debug" in result.value
    assert "--verbosity=quiet" not in result.value
