from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))


def _import_am_patch_modules() -> tuple[object, object, object, object]:
    from am_patch.engine import build_effective_policy
    from am_patch.errors import RunnerError
    from am_patch.patch_input import resolve_patch_plan
    from am_patch.startup_context import build_paths_and_logger

    return build_effective_policy, RunnerError, resolve_patch_plan, build_paths_and_logger


(
    build_effective_policy,
    RunnerError,
    resolve_patch_plan,
    build_paths_and_logger,
) = _import_am_patch_modules()


def _write_zip(path: Path, *, target: str | None, members: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if target is not None:
            zf.writestr("target.txt", target + "\n")
        for name, data in members.items():
            zf.writestr(name, data)


def _git_patch(relpath: str, old_text: str | None, new_text: str | None) -> bytes:
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        old = root / "old" / relpath
        new = root / "new" / relpath
        if old_text is not None:
            old.parent.mkdir(parents=True, exist_ok=True)
            old.write_text(old_text, encoding="utf-8")
        else:
            old.parent.mkdir(parents=True, exist_ok=True)
        if new_text is not None:
            new.parent.mkdir(parents=True, exist_ok=True)
            new.write_text(new_text, encoding="utf-8")
        else:
            new.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [
                "git",
                "diff",
                "--no-index",
                "--src-prefix=a/",
                "--dst-prefix=b/",
                str(old.relative_to(root)),
                str(new.relative_to(root)),
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 1, proc.stderr
        patch = proc.stdout
        patch = patch.replace(f"a/old/{relpath}", f"a/{relpath}")
        patch = patch.replace(f"b/new/{relpath}", f"b/{relpath}")
        return patch.encode("utf-8")


def _runner_tree(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    runner_root = tmp_path / "runner"
    import_root = runner_root / "scripts"
    package_dir = import_root / "am_patch"
    package_dir.mkdir(parents=True)
    target_repo = tmp_path / "target"
    target_repo.mkdir()
    other_repo = tmp_path / "other"
    other_repo.mkdir()
    cfg = package_dir / "am_patch.toml"
    cfg.write_text(
        "\n".join(
            [
                'target_repo_roots = ["../target", "../other"]',
                'active_target_repo_root = "../other"',
                'verbosity = "quiet"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return runner_root, import_root, target_repo, other_repo


def test_build_effective_policy_uses_patch_target_before_root_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner_root, import_root, target_repo, _ = _runner_tree(tmp_path)
    patch_root = runner_root / "patches"
    patch = _git_patch("docs/readme.txt", "old\n", "new\n")
    _write_zip(
        patch_root / "issue_25001_v1.zip",
        target="../target",
        members={"patches/per_file/docs__readme.txt.patch": patch},
    )

    monkeypatch.chdir(runner_root)
    monkeypatch.setattr(
        "am_patch.engine._detect_engine_roots",
        lambda module_file=None: (runner_root, import_root),
    )
    monkeypatch.setattr(
        "am_patch.startup_context._detect_runner_root",
        lambda module_file=None: runner_root,
    )

    res = build_effective_policy(["25001", "msg", "issue_25001_v1.zip"])
    assert not isinstance(res, int)
    cli, policy, config_path, used_cfg = res
    policy.ipc_socket_enabled = False
    ctx = build_paths_and_logger(cli, policy, config_path, used_cfg)

    assert policy.active_target_repo_root == "../target"
    assert policy._src["active_target_repo_root"] == "patch"
    assert ctx.repo_root == target_repo.resolve()


def test_cli_target_keeps_precedence_over_patch_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner_root, import_root, target_repo, other_repo = _runner_tree(tmp_path)
    patch_root = runner_root / "patches"
    patch = _git_patch("docs/readme.txt", "old\n", "new\n")
    _write_zip(
        patch_root / "issue_25001_v1.zip",
        target="../target",
        members={"patches/per_file/docs__readme.txt.patch": patch},
    )

    monkeypatch.chdir(runner_root)
    monkeypatch.setattr(
        "am_patch.engine._detect_engine_roots",
        lambda module_file=None: (runner_root, import_root),
    )
    monkeypatch.setattr(
        "am_patch.startup_context._detect_runner_root",
        lambda module_file=None: runner_root,
    )

    res = build_effective_policy(
        [
            "25001",
            "msg",
            "issue_25001_v1.zip",
            "--override",
            "active_target_repo_root=../other",
        ]
    )
    assert not isinstance(res, int)
    cli, policy, config_path, used_cfg = res
    policy.ipc_socket_enabled = False
    ctx = build_paths_and_logger(cli, policy, config_path, used_cfg)

    assert policy.active_target_repo_root == "../other"
    assert policy._src["active_target_repo_root"] == "cli"
    assert ctx.repo_root == other_repo.resolve()
    assert ctx.repo_root != target_repo.resolve()


def test_patch_target_must_obey_existing_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner_root, import_root, _, _ = _runner_tree(tmp_path)
    patch_root = runner_root / "patches"
    patch = _git_patch("docs/readme.txt", "old\n", "new\n")
    _write_zip(
        patch_root / "issue_25001_v1.zip",
        target="../denied",
        members={"patches/per_file/docs__readme.txt.patch": patch},
    )

    monkeypatch.chdir(runner_root)
    monkeypatch.setattr(
        "am_patch.engine._detect_engine_roots",
        lambda module_file=None: (runner_root, import_root),
    )
    monkeypatch.setattr(
        "am_patch.startup_context._detect_runner_root",
        lambda module_file=None: runner_root,
    )

    res = build_effective_policy(["25001", "msg", "issue_25001_v1.zip"])
    assert not isinstance(res, int)
    cli, policy, config_path, used_cfg = res
    policy.ipc_socket_enabled = False
    msg = "active_target_repo_root must resolve to runner_root or an entry from target_repo_roots"
    with pytest.raises(RunnerError, match=msg):
        build_paths_and_logger(cli, policy, config_path, used_cfg)


def test_zip_without_patch_members_remains_invalid_even_with_target(tmp_path: Path) -> None:
    patch_root = tmp_path / "patches"
    patch_path = patch_root / "issue_25001_v1.zip"
    _write_zip(patch_path, target="../target", members={})

    class _Cli:
        load_latest_patch = False
        patch_script = str(patch_path)

    class _Policy:
        unified_patch = False
        ascii_only_patch = True

    with pytest.raises(RunnerError, match="zip contains no .patch entries"):
        resolve_patch_plan(
            logger=None,
            cli=_Cli(),
            policy=_Policy(),
            issue_id=25001,
            repo_root=tmp_path,
            patch_root=patch_root,
        )
