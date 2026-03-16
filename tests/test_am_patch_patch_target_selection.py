from __future__ import annotations

import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest


def _import_target_selection():
    scripts_dir = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    from am_patch.config import Policy, policy_for_log
    from am_patch.errors import RunnerError
    from am_patch.patch_input import apply_patch_carried_target_selector_for_startup
    from am_patch.startup_context import build_paths_and_logger

    return (
        Policy,
        RunnerError,
        apply_patch_carried_target_selector_for_startup,
        build_paths_and_logger,
        policy_for_log,
    )


def _write_patch_zip(path: Path, *, target_text: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("patches/per_file/demo.py.patch", "--- a/demo.py\n+++ b/demo.py\n")
        if target_text is not None:
            zf.writestr("target.txt", target_text)


def test_patch_carried_target_overrides_config_target_before_root_binding(
    tmp_path: Path,
) -> None:
    (
        policy_cls,
        _,
        apply_patch_carried_target_selector_for_startup,
        build_paths_and_logger,
        policy_for_log,
    ) = _import_target_selection()

    target_repo = tmp_path / "target-repo"
    target_repo.mkdir()
    patch_dir = tmp_path / "patches"
    _write_patch_zip(
        patch_dir / "issue_999.zip",
        target_text=f"{target_repo.as_posix()}\n",
    )

    policy = policy_cls()
    policy.patch_dir = str(patch_dir)
    policy.repo_root = str(tmp_path / "config-target")
    policy.target_repo_roots = [str(target_repo)]
    policy.current_log_symlink_enabled = False
    policy.verbosity = "quiet"
    policy.log_level = "warning"
    policy.json_out = False
    policy.ipc_socket_enabled = False

    cli = SimpleNamespace(
        issue_id="999",
        mode="workspace",
        patch_script=None,
        load_latest_patch=None,
    )
    cfg = tmp_path / "am_patch_test.toml"
    cfg.write_text("", encoding="utf-8")

    apply_patch_carried_target_selector_for_startup(
        cli=cli,
        policy=policy,
        issue_id=999,
        runner_root=Path(__file__).resolve().parent.parent,
    )
    assert policy.active_target_repo_root == target_repo.as_posix()
    assert policy._src["active_target_repo_root"] == "patch-carried"

    ctx = build_paths_and_logger(cli, policy, cfg, "test")
    try:
        assert ctx.repo_root == target_repo.resolve()
        policy_text = policy_for_log(policy)
        assert "src=patch-carried" in policy_text
        assert f"active_target_repo_root='{target_repo.as_posix()}'" in policy_text
    finally:
        ctx.status.stop()
        ctx.logger.close()


def test_patch_carried_target_respects_explicit_cli_target(tmp_path: Path) -> None:
    (
        policy_cls,
        _,
        apply_patch_carried_target_selector_for_startup,
        _,
        _,
    ) = _import_target_selection()

    target_repo = tmp_path / "target-repo"
    target_repo.mkdir()
    patch_dir = tmp_path / "patches"
    _write_patch_zip(
        patch_dir / "issue_999.zip",
        target_text=f"{target_repo.as_posix()}\n",
    )

    policy = policy_cls()
    policy.patch_dir = str(patch_dir)
    policy.active_target_repo_root = "/tmp/cli-target"
    policy._src["active_target_repo_root"] = "cli"

    cli = SimpleNamespace(
        issue_id="999",
        mode="workspace",
        patch_script=None,
        load_latest_patch=None,
    )

    apply_patch_carried_target_selector_for_startup(
        cli=cli,
        policy=policy,
        issue_id=999,
        runner_root=Path(__file__).resolve().parent.parent,
    )

    assert policy.active_target_repo_root == "/tmp/cli-target"
    assert policy._src["active_target_repo_root"] == "cli"


def test_patch_carried_target_rejects_multiline_target_metadata(tmp_path: Path) -> None:
    policy_cls, runner_error_cls, apply_patch_carried_target_selector_for_startup, _, _ = (
        _import_target_selection()
    )

    patch_dir = tmp_path / "patches"
    _write_patch_zip(
        patch_dir / "issue_999.zip",
        target_text="target-a\ntarget-b\n",
    )

    policy = policy_cls()
    policy.patch_dir = str(patch_dir)
    cli = SimpleNamespace(
        issue_id="999",
        mode="workspace",
        patch_script=None,
        load_latest_patch=None,
    )

    with pytest.raises(runner_error_cls) as excinfo:
        apply_patch_carried_target_selector_for_startup(
            cli=cli,
            policy=policy,
            issue_id=999,
            runner_root=Path(__file__).resolve().parent.parent,
        )

    assert excinfo.value.stage == "PREFLIGHT"
    assert excinfo.value.category == "PATCH_PATH"
    assert "target.txt must contain exactly one non-empty line" in excinfo.value.message
