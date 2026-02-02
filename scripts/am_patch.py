#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import os
import shutil
import sys
from contextlib import suppress
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_VENV_PY = _REPO_ROOT / ".venv" / "bin" / "python"

if os.environ.get("AM_PATCH_VENV_BOOTSTRAPPED") != "1":
    if not _VENV_PY.exists():
        print(f"[am_patch_v2] ERROR: venv python not found: {_VENV_PY}", file=sys.stderr)
        print(
            "[am_patch_v2] Hint: create venv at repo/.venv and install dev deps "
            "(ruff/pytest/mypy).",
            file=sys.stderr,
        )
        raise SystemExit(2)

    cur = Path(sys.executable).resolve()
    # If current interpreter is not under repo/.venv, switch to it.
    if ".venv" not in str(cur):
        os.environ["AM_PATCH_VENV_BOOTSTRAPPED"] = "1"
        os.execv(str(_VENV_PY), [str(_VENV_PY), *sys.argv])

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from am_patch import git_ops
from am_patch.audit_rubric_check import check_audit_rubric_coverage
from am_patch.cli import parse_args
from am_patch.config import Policy, apply_cli_overrides, build_policy, load_config, policy_for_log
from am_patch.errors import RunnerError, fingerprint
from am_patch.lock import FileLock
from am_patch.log import Logger, new_log_file
from am_patch.manifest import load_files
from am_patch.patch_exec import precheck_patch_script, run_patch, run_unified_patch_bundle
from am_patch.patch_select import PatchSelectError, choose_default_patch_input, decide_unified_mode
from am_patch.paths import default_paths, ensure_dirs
from am_patch.scope import blessed_gate_outputs_in, changed_paths, enforce_scope_delta
from am_patch.version import RUNNER_VERSION
from am_patch.workspace import (
    create_checkpoint,
    delete_workspace,
    drop_checkpoint,
    ensure_workspace,
    open_existing_workspace,
    rollback_to_checkpoint,
)


def _fs_junk_ignore_partition(paths: list[str]) -> tuple[list[str], list[str]]:
    """Partition paths into (kept, ignored) for workspace->live promotion hygiene."""
    prefixes = (
        ".am_patch/",
        ".pytest_cache/",
        ".mypy_cache/",
        ".ruff_cache/",
        "__pycache__/",
    )
    suffixes = (".pyc",)
    kept: list[str] = []
    ignored: list[str] = []
    for p in paths:
        pp = p.strip()
        if not pp:
            continue
        is_ignored = False
        for pre in prefixes:
            if pp == pre.rstrip("/") or pp.startswith(pre):
                is_ignored = True
                break
        if not is_ignored and "/__pycache__/" in pp:
            is_ignored = True
        if not is_ignored:
            for suf in suffixes:
                if pp.endswith(suf):
                    is_ignored = True
                    break
        if is_ignored:
            ignored.append(pp)
        else:
            kept.append(pp)

    # unique preserve order
    def _uniq(xs: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for x in xs:
            if x in seen:
                continue
            seen.add(x)
            out.append(x)
        return out

    return _uniq(kept), _uniq(ignored)


def _run_post_success_audit(logger: Logger, repo_root: Path, policy: Policy) -> None:
    """Run audit/audit_report.py after a successful push (best effort, deterministic)."""
    logger.section("AUDIT")
    if not policy.post_success_audit:
        logger.line("audit_report=SKIP (post_success_audit=false)")
        return

    r = logger.run_logged([sys.executable, "-u", "audit/audit_report.py"], cwd=repo_root)
    if r.returncode != 0:
        raise RunnerError("AUDIT", "AUDIT_REPORT_FAILED", "audit/audit_report.py failed")


from am_patch.archive import archive_patch, make_failure_zip
from am_patch.gates import run_gates
from am_patch.promote import promote_files
from am_patch.state import load_state, save_state, update_union


def _resolve_repo_root() -> Path:
    import subprocess

    p = subprocess.run(["git", "rev-parse", "--show-toplevel"], text=True, capture_output=True)
    if p.returncode == 0 and p.stdout.strip():
        return Path(p.stdout.strip())
    return Path.cwd()


def _is_under(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _select_latest_issue_patch(*, patch_dir: Path, issue_id: str, hint_name: str | None) -> Path:
    """Select the most recent patch script for ISSUE_ID from patches/, patches/successful/,
    patches/unsuccessful/.

    If hint_name is provided, it is treated as a filename hint (basename). The selection
    prefers that exact name and its archive variants (stem_vN.py). If no hint is provided,
    any script starting with "issue_<id>" is eligible.

    Selection order: newest mtime wins; ties broken by lexical path.
    """
    dirs = [patch_dir, patch_dir / "successful", patch_dir / "unsuccessful"]

    def iter_files(d: Path) -> list[Path]:
        """Return candidate archived patch inputs for -l.

        Supported inputs:
        - *.py   (patch script)
        - *.patch (unified diff)
        - *.zip  (bundle containing at least one *.patch entry)
        """
        import zipfile

        try:
            out: list[Path] = []
            for p in d.iterdir():
                if not p.is_file():
                    continue
                if p.suffix in (".py", ".patch"):
                    out.append(p)
                    continue
                if p.suffix == ".zip":
                    try:
                        with zipfile.ZipFile(p, "r") as z:
                            if any(n.endswith(".patch") for n in z.namelist()):
                                out.append(p)
                    except zipfile.BadZipFile:
                        # Ignore invalid zip files in archive dirs (deterministic: not candidates).
                        continue
            return out
        except FileNotFoundError:
            return []

    issue_prefix = f"issue_{issue_id}"
    hint_stem: str | None = None
    if hint_name:
        bn = Path(hint_name).name
        hint_stem = Path(bn).stem

    cands: list[Path] = []
    for d in dirs:
        for p in iter_files(d):
            name = p.name
            # If a hint_name was provided (explicit patch filename), select by basename
            # (and its _vN archive variants) regardless of ISSUE_ID prefix.
            if hint_stem is not None:
                if p.stem == hint_stem:
                    cands.append(p)
                    continue
                if p.stem.startswith(f"{hint_stem}_v"):
                    tail = p.stem[len(hint_stem) + 2 :]
                    if tail.isdigit():
                        cands.append(p)
                        continue
                continue

            # Otherwise (no hint), select by ISSUE_ID prefix.
            if not name.startswith(issue_prefix):
                continue
            cands.append(p)

    if not cands:
        raise RunnerError(
            "PREFLIGHT", "MANIFEST", f"-l: no archived patch scripts found for issue_id={issue_id}"
        )

    cands.sort(key=lambda p: (p.stat().st_mtime, str(p)), reverse=True)
    return cands[0]


def _workspace_history_dirs(ws_root: Path) -> tuple[Path, Path, Path, Path]:
    logs_dir = ws_root / "logs"
    oldlogs_dir = ws_root / "oldlogs"
    patches_dir = ws_root / "patches"
    oldpatches_dir = ws_root / "oldpatches"
    for d in [logs_dir, oldlogs_dir, patches_dir, oldpatches_dir]:
        d.mkdir(parents=True, exist_ok=True)
    return logs_dir, oldlogs_dir, patches_dir, oldpatches_dir


def _rotate_current_dir(cur_dir: Path, old_dir: Path, prev_attempt: int) -> None:
    if prev_attempt <= 0:
        return
    old_dir.mkdir(parents=True, exist_ok=True)
    for p in sorted(cur_dir.glob("*")):
        if not p.is_file():
            continue
        new_name = f"{p.stem}_[attempt{prev_attempt}]{p.suffix}"
        p.replace(old_dir / new_name)


def _workspace_store_current_patch(ws, patch_script: Path) -> None:
    logs_dir, oldlogs_dir, patches_dir, oldpatches_dir = _workspace_history_dirs(ws.root)
    _ = logs_dir
    _ = oldlogs_dir

    prev_attempt = int(ws.attempt) - 1
    _rotate_current_dir(patches_dir, oldpatches_dir, prev_attempt)

    # Keep the current patch under its original filename (no suffix).
    dst = patches_dir / patch_script.name
    shutil.copy2(patch_script, dst)


def _workspace_store_current_log(ws, log_path: Path) -> None:
    logs_dir, oldlogs_dir, patches_dir, oldpatches_dir = _workspace_history_dirs(ws.root)
    _ = patches_dir
    _ = oldpatches_dir

    prev_attempt = int(ws.attempt) - 1
    _rotate_current_dir(logs_dir, oldlogs_dir, prev_attempt)

    # Keep the current log under its original filename (no suffix).
    dst = logs_dir / log_path.name
    shutil.copy2(log_path, dst)


def main(argv: list[str]) -> int:
    cli = parse_args(argv)

    defaults = Policy()
    config_path = Path(__file__).resolve().parent / "am_patch" / "am_patch.toml"
    cfg, used_cfg = load_config(config_path)
    policy = build_policy(defaults, cfg)

    apply_cli_overrides(
        policy,
        {
            "run_all_tests": cli.run_all_tests,
            "allow_no_op": cli.allow_no_op,
            "skip_up_to_date": cli.skip_up_to_date,
            "allow_non_main": cli.allow_non_main,
            "no_rollback": cli.no_rollback,
            "success_archive_name": getattr(cli, "success_archive_name", None),
            "update_workspace": cli.update_workspace,
            "gates_allow_fail": cli.allow_gates_fail,
            "gates_skip_ruff": cli.skip_ruff,
            "gates_skip_pytest": cli.skip_pytest,
            "gates_skip_mypy": cli.skip_mypy,
            "gates_order": (
                []
                if (
                    getattr(cli, "gates_order", None) is not None
                    and str(cli.gates_order).strip() == ""
                )
                else ([s.strip().lower() for s in str(cli.gates_order).split(",") if s.strip()])
                if getattr(cli, "gates_order", None) is not None
                else None
            ),
            "ruff_autofix_legalize_outside": getattr(cli, "ruff_autofix_legalize_outside", None),
            "soft_reset_workspace": cli.soft_reset_workspace,
            "enforce_allowed_files": cli.enforce_allowed_files,
            # New safety + gate controls
            "rollback_workspace_on_fail": getattr(cli, "rollback_workspace_on_fail", None),
            "live_repo_guard": getattr(cli, "live_repo_guard", None),
            "patch_jail": getattr(cli, "patch_jail", None),
            "patch_jail_unshare_net": getattr(cli, "patch_jail_unshare_net", None),
            "ruff_format": getattr(cli, "ruff_format", None),
            "pytest_use_venv": getattr(cli, "pytest_use_venv", None),
            "compile_check": getattr(cli, "compile_check", None),
            "post_success_audit": getattr(cli, "post_success_audit", None),
            "test_mode": getattr(cli, "test_mode", None),
            "unified_patch": getattr(cli, "unified_patch", None),
            "unified_patch_strip": getattr(cli, "patch_strip", None),
            "overrides": getattr(cli, "overrides", None),
        },
    )

    # Group B: map extra CLI flags onto policy keys (symmetry helpers)
    if getattr(cli, "require_push_success", None):
        policy.allow_push_fail = False
        policy._src["allow_push_fail"] = "cli"
    if getattr(cli, "disable_promotion", None):
        policy.commit_and_push = False
        policy._src["commit_and_push"] = "cli"
    if getattr(cli, "allow_live_changed", None):
        policy.fail_if_live_files_changed = False
        policy._src["fail_if_live_files_changed"] = "cli"
        policy.live_changed_resolution = "overwrite_live"
        policy._src["live_changed_resolution"] = "cli"
    if getattr(cli, "keep_workspace", None):
        policy.delete_workspace_on_success = False
        policy._src["delete_workspace_on_success"] = "cli"
    if getattr(cli, "allow_outside_files", None):
        policy.allow_outside_files = True
        policy._src["allow_outside_files"] = "cli"
    if getattr(cli, "allow_declared_untouched", None):
        policy.allow_declared_untouched = True
        policy._src["allow_declared_untouched"] = "cli"

    if cli.mode == "show_config":
        # Print the same effective config/policy that is normally logged at the start of a run.
        # No workspace, no log file, no side effects.
        print(f"config_path={config_path} used={used_cfg}")
        print(policy_for_log(policy))
        return 0

    if policy.test_mode and cli.mode != "workspace":
        raise SystemExit("test-mode is supported only in workspace mode")

    repo_root = Path(policy.repo_root) if policy.repo_root else _resolve_repo_root()
    patch_dir = Path(policy.patch_dir) if policy.patch_dir else (repo_root / "patches")
    paths = default_paths(repo_root=repo_root, patch_dir=patch_dir)
    ensure_dirs(paths)

    log_path = new_log_file(paths.logs_dir, cli.issue_id)
    logger = Logger(log_path=log_path, symlink_path=paths.symlink_path, tee_to_screen=True)

    lock = FileLock(paths.lock_path)
    exit_code: int = 0
    patch_script: Path | None = None
    used_patch_for_zip: Path | None = None
    files_for_fail_zip: list[str] = []
    failed_patch_blobs_for_zip: list[tuple[str, bytes]] = []
    patch_applied_successfully: bool = False
    rollback_ckpt_for_posthook = None
    rollback_ws_for_posthook = None

    delete_workspace_after_archive: bool = False
    ws_for_posthook = None
    push_ok_for_posthook: bool | None = None
    try:
        logger.section("AM_PATCH START")
        logger.line(f"RUNNER_VERSION={RUNNER_VERSION}")
        logger.line(f"repo_root={repo_root}")
        logger.line(f"patch_dir={patch_dir}")
        logger.line(f"config_path={config_path} used={used_cfg}")
        logger.line(f"log_path={log_path}")
        logger.line(f"symlink_path={paths.symlink_path} -> logs/{log_path.name}")
        logger.section("EFFECTIVE CONFIG")
        logger.line(policy_for_log(policy))

        lock.acquire()

        if cli.mode == "finalize_workspace":
            # Finalize an existing workspace: gates in workspace, then promote to live, then
            # gates+commit+push in live.
            issue_id = cli.issue_id
            assert issue_id is not None

            ws = open_existing_workspace(logger, paths.workspaces_dir, issue_id)
            logger.section("FINALIZE WORKSPACE")
            logger.line(f"workspace_root={ws.root}")
            logger.line(f"workspace_repo={ws.repo}")
            logger.line(f"workspace_meta={ws.meta_path}")
            logger.line(f"workspace_base_sha={ws.base_sha}")

            # Commit message is always sourced from workspace meta.json.
            if not ws.message or not str(ws.message).strip():
                raise RunnerError(
                    "PREFLIGHT", "WORKSPACE", "workspace meta.json missing non-empty message"
                )

            # Gates in workspace first.

            run_gates(
                logger,
                cwd=ws.repo,
                repo_root=repo_root,
                run_all=policy.run_all_tests,
                compile_check=policy.compile_check,
                compile_targets=policy.compile_targets,
                compile_exclude=policy.compile_exclude,
                allow_fail=policy.gates_allow_fail,
                skip_ruff=policy.gates_skip_ruff,
                skip_pytest=policy.gates_skip_pytest,
                skip_mypy=policy.gates_skip_mypy,
                ruff_format=policy.ruff_format,
                ruff_autofix=policy.ruff_autofix,
                ruff_targets=policy.ruff_targets,
                pytest_targets=policy.pytest_targets,
                mypy_targets=policy.mypy_targets,
                gates_order=policy.gates_order,
                pytest_use_venv=policy.pytest_use_venv,
            )

            changed_all = changed_paths(logger, ws.repo)
            promote_list, ignored = _fs_junk_ignore_partition(changed_all)
            logger.section("PROMOTION PLAN")
            logger.line(f"changed_all={changed_all}")
            logger.line(f"ignored_paths={ignored}")
            logger.line(f"files_to_promote={promote_list}")
            if not promote_list:
                raise RunnerError("PREFLIGHT", "WORKSPACE", "no promotable workspace changes")

            promote_files(
                logger=logger,
                workspace_repo=ws.repo,
                live_repo=repo_root,
                base_sha=ws.base_sha,
                files_to_promote=promote_list,
                fail_if_live_changed=policy.fail_if_live_files_changed,
                live_changed_resolution=policy.live_changed_resolution,
            )

            # Gates in live repo.
            run_gates(
                logger,
                cwd=repo_root,
                repo_root=repo_root,
                run_all=policy.run_all_tests,
                compile_check=policy.compile_check,
                compile_targets=policy.compile_targets,
                compile_exclude=policy.compile_exclude,
                allow_fail=policy.gates_allow_fail,
                skip_ruff=policy.gates_skip_ruff,
                skip_pytest=policy.gates_skip_pytest,
                skip_mypy=policy.gates_skip_mypy,
                ruff_format=policy.ruff_format,
                ruff_autofix=policy.ruff_autofix,
                ruff_targets=policy.ruff_targets,
                pytest_targets=policy.pytest_targets,
                mypy_targets=policy.mypy_targets,
                gates_order=policy.gates_order,
                pytest_use_venv=policy.pytest_use_venv,
            )

            sha: str | None = None
            push_ok: bool | None = None
            if policy.commit_and_push:
                sha = git_ops.commit(logger, repo_root, str(ws.message))
                push_ok = git_ops.push(
                    logger,
                    repo_root,
                    policy.default_branch,
                    allow_fail=policy.allow_push_fail,
                )

            logger.section("SUCCESS")
            if policy.commit_and_push:
                logger.line(f"commit_sha={sha}")
                if push_ok is True:
                    logger.line("push=OK")
                else:
                    if policy.allow_push_fail:
                        logger.line("push=FAILED_ALLOWED")
                    else:
                        logger.line("push=FAILED")
            else:
                logger.line("commit_sha=SKIPPED")
                logger.line("push=SKIPPED")

            # Cleanup: mirror workspace-mode behavior.
            # Delete workspace on success unless policy.delete_workspace_on_success is false.
            #
            # When promotion is disabled (no commit/push), keep the workspace even if the
            # default policy would delete it. This avoids losing an easy re-run path while
            # the live repo has uncommitted changes.
            workspace_deleted = False
            if policy.delete_workspace_on_success and policy.commit_and_push:
                delete_workspace(logger, ws)
                workspace_deleted = True
            elif policy.delete_workspace_on_success and not policy.commit_and_push:
                logger.line("workspace_delete=SKIPPED (disable-promotion)")

            # Post-success audit: show current audit progress after SUCCESS and workspace cleanup.
            # Runs on the live repo (repo_root), not the workspace.
            if push_ok is True and workspace_deleted:
                _run_post_success_audit(logger, repo_root, policy)

            return 0

        if cli.mode == "finalize":
            git_ops.fetch(logger, repo_root)
            if policy.require_up_to_date and not policy.skip_up_to_date:
                git_ops.require_up_to_date(logger, repo_root, policy.default_branch)
            if policy.enforce_main_branch and not policy.allow_non_main:
                git_ops.require_branch(logger, repo_root, policy.default_branch)

            run_gates(
                logger,
                cwd=repo_root,
                repo_root=repo_root,
                run_all=policy.run_all_tests,
                compile_check=policy.compile_check,
                compile_targets=policy.compile_targets,
                compile_exclude=policy.compile_exclude,
                allow_fail=policy.gates_allow_fail,
                skip_ruff=policy.gates_skip_ruff,
                skip_pytest=policy.gates_skip_pytest,
                skip_mypy=policy.gates_skip_mypy,
                ruff_format=policy.ruff_format,
                ruff_autofix=policy.ruff_autofix,
                ruff_targets=policy.ruff_targets,
                pytest_targets=policy.pytest_targets,
                mypy_targets=policy.mypy_targets,
                gates_order=policy.gates_order,
                pytest_use_venv=policy.pytest_use_venv,
            )
            sha: str | None = None
            push_ok: bool | None = None
            if policy.commit_and_push:
                sha = git_ops.commit(logger, repo_root, cli.message or "finalize")
                push_ok = git_ops.push(
                    logger,
                    repo_root,
                    policy.default_branch,
                    allow_fail=policy.allow_push_fail,
                )

            logger.section("SUCCESS")
            if policy.commit_and_push:
                logger.line(f"commit_sha={sha}")
                if push_ok is True:
                    logger.line("push=OK")
                else:
                    if policy.allow_push_fail:
                        logger.line("push=FAILED_ALLOWED")
                    else:
                        logger.line("push=FAILED")
            else:
                logger.line("commit_sha=SKIPPED")
                logger.line("push=SKIPPED")

            if push_ok is True:
                _run_post_success_audit(logger, repo_root, policy)
            return 0

        issue_id = cli.issue_id
        assert issue_id is not None

        patch_script: Path | None = None

        if getattr(cli, "load_latest_patch", None):
            hint_name = Path(cli.patch_script).name if cli.patch_script else None
            patch_script = _select_latest_issue_patch(
                patch_dir=patch_dir, issue_id=issue_id, hint_name=hint_name
            )
        elif cli.patch_script:
            raw = Path(cli.patch_script)
            if raw.is_absolute():
                patch_script = raw
            else:
                # Accept either:
                #  - a path relative to CWD (e.g. patches/issue_999.py), OR
                #  - a bare filename resolved under patch_dir (e.g. issue_999.py).
                cand_cwd = (Path.cwd() / raw).resolve()
                cand_patchdir = (patch_dir / raw).resolve()
                if cand_cwd.exists() and _is_under(cand_cwd, patch_dir):
                    patch_script = cand_cwd
                elif cand_patchdir.exists():
                    patch_script = cand_patchdir
                else:
                    raise RunnerError(
                        "PREFLIGHT",
                        "MANIFEST",
                        f"patch script not found (tried: {cand_cwd} and {cand_patchdir})",
                    )
        else:
            try:
                patch_script = choose_default_patch_input(patch_dir, issue_id)
            except PatchSelectError as e:
                raise RunnerError("PREFLIGHT", "MANIFEST", str(e)) from e

        if not patch_script.exists():
            raise RunnerError("PREFLIGHT", "MANIFEST", f"patch script not found: {patch_script}")

        # Enforce patch script location: must be under patch_dir.
        if not _is_under(patch_script, patch_dir):
            raise RunnerError(
                "PREFLIGHT",
                "PATCH_PATH",
                f"patch script must be under {patch_dir} (got {patch_script})",
            )
        try:
            unified_mode = decide_unified_mode(
                patch_script, explicit_unified=bool(getattr(policy, "unified_patch", False))
            )
        except PatchSelectError as e:
            raise RunnerError("PREFLIGHT", "PATCH_PATH", str(e)) from e

        if not unified_mode:
            precheck_patch_script(patch_script, ascii_only=policy.ascii_only_patch)

        # Audit rubric guard (future-proofing): fail fast when new audit domains are added
        # but audit/audit_rubric.yaml does not contain the required runtime evidence commands.
        if getattr(policy, "audit_rubric_guard", True):
            missing = check_audit_rubric_coverage(repo_root)
            if missing:
                # Build a deterministic, copy-paste friendly guidance message.
                lines: list[str] = []
                lines.append(
                    "audit rubric guard failed: missing required runtime evidence commands in "
                    "audit/audit_rubric.yaml"
                )
                lines.append("")
                lines.append(
                    "Add these command(s) to audit/audit_rubric.yaml (under "
                    "runtime_evidence.commands, and mark required: true):"
                )
                lines.append("")
                for m in missing:
                    lines.append(
                        f"- domain={m.domain} cli={m.cli_name} caps={','.join(m.capabilities)}"
                    )
                    for c in m.missing_commands:
                        lines.append(f"  - {c} --format yaml")
                lines.append("")
                lines.append("Then re-run runtime evidence to verify:")
                lines.append(
                    "  python3 audit/run_runtime_evidence.py --repo . --rubric "
                    "audit/audit_rubric.yaml"
                )
                raise RunnerError("PREFLIGHT", "CONFIG", "\n".join(lines))

        # Git preflight (live repo)
        git_ops.fetch(logger, repo_root)
        if policy.require_up_to_date and not policy.skip_up_to_date:
            git_ops.require_up_to_date(logger, repo_root, policy.default_branch)
        if policy.enforce_main_branch and not policy.allow_non_main:
            git_ops.require_branch(logger, repo_root, policy.default_branch)

        base_sha = git_ops.head_sha(logger, repo_root)
        files_current = [] if unified_mode else load_files(patch_script)

        logger.section("DECLARED FILES")
        for _p in files_current:
            logger.line(_p)

        ws = ensure_workspace(
            logger=logger,
            workspaces_dir=paths.workspaces_dir,
            issue_id=issue_id,
            live_repo=repo_root,
            base_sha=base_sha,
            update=policy.update_workspace,
            soft_reset=policy.soft_reset_workspace,
            message=cli.message,
        )
        ws_for_posthook = ws
        _workspace_store_current_patch(ws, patch_script)
        logger.section("WORKSPACE META")
        logger.line(f"workspace_root={ws.root}")
        logger.line(f"workspace_repo={ws.repo}")
        logger.line(f"workspace_base_sha={ws.base_sha}")
        logger.line(f"attempt={ws.attempt}")

        # Load per-issue cumulative state (allowed union).
        st = load_state(ws.root, ws.base_sha)
        logger.section("ISSUE STATE (before)")
        logger.line(f"allowed_union={sorted(st.allowed_union)}")

        # Optional live repo guard (must stay unchanged until promotion).
        live_guard_before: str | None = None
        if policy.live_repo_guard:
            logger.section("LIVE REPO GUARD (before)")
            r = logger.run_logged(
                ["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo_root
            )
            live_guard_before = r.stdout or ""
            logger.line(f"live_repo_porcelain_len={len(live_guard_before)}")

        ckpt = create_checkpoint(logger, ws.repo, enabled=policy.rollback_workspace_on_fail)

        # Baseline changes BEFORE running patch (so scope is delta).
        before = changed_paths(logger, ws.repo)

        try:
            touched_for_zip: list[str] = []
            failed_patch_blobs: list[tuple[str, bytes]] = []
            patch_applied_any = False

            if unified_mode:
                res = run_unified_patch_bundle(
                    logger,
                    patch_script,
                    workspace_repo=ws.repo,
                    policy=policy,
                )
                patch_applied_any = res.applied_ok > 0
                files_current = list(res.declared_files)
                touched_for_zip = list(res.touched_files)
                failed_patch_blobs = [(f.name, f.data) for f in res.failures]

                # For patched.zip on failure: always include touched targets and failed patch blobs.
                # This must be available even if scope enforcement fails later.
                files_for_fail_zip = sorted(set(touched_for_zip) | set(files_current))
                failed_patch_blobs_for_zip = list(failed_patch_blobs)
                patch_applied_successfully = patch_applied_any

            else:
                run_patch(logger, patch_script, workspace_repo=ws.repo, policy=policy)
                patch_applied_any = True

            after = changed_paths(logger, ws.repo)
            touched = enforce_scope_delta(
                logger,
                files_current=files_current,
                before=before,
                after=after,
                no_op_fail=policy.no_op_fail,
                allow_no_op=policy.allow_no_op,
                allow_outside_files=policy.allow_outside_files,
                declared_untouched_fail=policy.declared_untouched_fail,
                allow_declared_untouched=policy.allow_declared_untouched,
            )

            # Snapshot dirty paths immediately after patch (before gates).
            dirty_after_patch = list(after)

            # For patched.zip on failure: include changed files plus all touched targets
            # (including failed patches).
            files_for_fail_zip = sorted(set(touched) | set(touched_for_zip))
            failed_patch_blobs_for_zip = list(failed_patch_blobs)
            patch_applied_successfully = patch_applied_any

        except Exception:
            # Defer rollback until after diagnostics archive is created.
            rollback_ckpt_for_posthook = ckpt
            rollback_ws_for_posthook = ws
            raise

        # Live repo guard: after patching (before gates) if scope includes patch.
        if (
            policy.live_repo_guard
            and live_guard_before is not None
            and policy.live_repo_guard_scope == "patch"
        ):
            logger.section("LIVE REPO GUARD (after patch)")
            r2 = logger.run_logged(
                ["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo_root
            )
            live_guard_after = r2.stdout or ""
            logger.line(f"live_repo_porcelain_len={len(live_guard_after)}")
            if live_guard_after != live_guard_before:
                raise RunnerError(
                    "SECURITY",
                    "LIVE_REPO_CHANGED",
                    "live repo changed during patching (expected no changes)",
                )

        # Update union AFTER patch success (even if this run was noop with -n).
        st = update_union(st, files_current)
        if policy.allow_outside_files:
            # Spec: -a must also legalize any touched paths into allowed_union for this ISSUE_ID.
            st = update_union(st, touched)
            logger.line(f"legalized_outside_files={sorted(set(touched) - set(files_current))}")
        save_state(ws.root, st)
        logger.section("ISSUE STATE (after)")
        logger.line(f"allowed_union={sorted(st.allowed_union)}")

        # Gates in workspace (NO rollback)
        run_gates(
            logger,
            cwd=ws.repo,
            repo_root=repo_root,
            run_all=policy.run_all_tests,
            compile_check=policy.compile_check,
            compile_targets=policy.compile_targets,
            compile_exclude=policy.compile_exclude,
            allow_fail=policy.gates_allow_fail,
            skip_ruff=policy.gates_skip_ruff,
            skip_pytest=policy.gates_skip_pytest,
            skip_mypy=policy.gates_skip_mypy,
            ruff_format=policy.ruff_format,
            ruff_autofix=policy.ruff_autofix,
            ruff_targets=policy.ruff_targets,
            pytest_targets=policy.pytest_targets,
            mypy_targets=policy.mypy_targets,
            gates_order=policy.gates_order,
            pytest_use_venv=policy.pytest_use_venv,
        )

        # Live repo guard: optionally also after gates.
        if (
            policy.live_repo_guard
            and live_guard_before is not None
            and policy.live_repo_guard_scope == "patch_and_gates"
        ):
            logger.section("LIVE REPO GUARD (after gates)")
            r2 = logger.run_logged(
                ["git", "status", "--porcelain", "--untracked-files=all"], cwd=repo_root
            )
            live_guard_after = r2.stdout or ""
            logger.line(f"live_repo_porcelain_len={len(live_guard_after)}")
            if live_guard_after != live_guard_before:
                raise RunnerError(
                    "SECURITY",
                    "LIVE_REPO_CHANGED",
                    "live repo changed during patching/gates (expected no changes)",
                )

        if policy.test_mode:
            logger.section("TEST MODE")
            logger.line("TEST_MODE=1")
            logger.line("TEST_MODE_STOP=AFTER_WORKSPACE_GATES_AND_LIVE_GUARD")
            logger.line(
                "STOP: test mode (no promotion, no live gates, no commit/push, no archives)"
            )
            return 0

        # Determine what to promote/commit: all current dirty paths within allowed_union.
        dirty_all = changed_paths(logger, ws.repo)

        # Ruff autofix may introduce additional changes after the patch. When enabled,
        # automatically legalize ruff-only changes outside FILES (bounded to ruff_targets).
        if policy.ruff_autofix and getattr(policy, "ruff_autofix_legalize_outside", True):
            patch_set = set(dirty_after_patch)
            now_set = set(dirty_all)
            ruff_only = sorted(p for p in (now_set - patch_set) if p)
            if ruff_only:

                def _under_targets(rel: str) -> bool:
                    for t in policy.ruff_targets:
                        t = (t or "").strip().rstrip("/")
                        if not t:
                            continue
                        if rel == t or rel.startswith(t + "/"):
                            return True
                    return False

                legalized = sorted([p for p in ruff_only if _under_targets(p)])
                if legalized:
                    st = update_union(st, legalized)
                    save_state(ws.root, st)
                    logger.line(f"legalized_ruff_autofix_files={legalized}")
        allowed_union = set(st.allowed_union)
        dirty_allowed = [p for p in dirty_all if p in allowed_union]
        dirty_blessed = blessed_gate_outputs_in(dirty_all)
        # Promote allowed_union paths + blessed gate outputs (without requiring -a).
        to_promote: list[str] = []
        seen_tp: set[str] = set()
        for pp in dirty_allowed + dirty_blessed:
            if pp in seen_tp:
                continue
            seen_tp.add(pp)
            to_promote.append(pp)

        logger.section("PROMOTION PLAN")
        logger.line(f"dirty_all={dirty_all}")
        logger.line(f"dirty_allowed={dirty_allowed}")
        logger.line(f"dirty_blessed={dirty_blessed}")
        logger.line(f"files_to_promote={to_promote}")

        promote_files(
            logger=logger,
            workspace_repo=ws.repo,
            live_repo=repo_root,
            base_sha=ws.base_sha,
            files_to_promote=to_promote,
            fail_if_live_changed=policy.fail_if_live_files_changed
            and (not policy.update_workspace),
            live_changed_resolution=policy.live_changed_resolution,
        )

        sha = ""
        push_ok: bool | None = None
        if policy.commit_and_push:
            sha = git_ops.commit(
                logger, repo_root, (ws.message or f"Issue {issue_id}: apply patch")
            )
            push_ok = git_ops.push(
                logger, repo_root, policy.default_branch, allow_fail=policy.allow_push_fail
            )

        push_ok_for_posthook = push_ok

        used_patch_for_zip = archive_patch(logger, patch_script, paths.successful_dir)

        drop_checkpoint(logger, ws.repo, ckpt)

        delete_workspace_after_archive = bool(policy.delete_workspace_on_success)

        logger.section("SUCCESS")
        if sha:
            logger.line(f"commit_sha={sha}")
        if policy.commit_and_push:
            if push_ok is True:
                logger.line("push=OK")
            elif push_ok is False:
                if policy.allow_push_fail:
                    logger.line("push=FAILED_ALLOWED")
                else:
                    logger.line("push=FAILED")
            else:
                logger.line("push=UNKNOWN")
        else:
            logger.line("push=SKIPPED")
        return 0

    except RunnerError as e:
        exit_code = 1
        logger.section("FAILURE")
        logger.line(str(e))
        logger.line(fingerprint(e))
        return 1
    finally:
        # Posthook: always create an archive after a workspace-mode run.
        # - on failure: patched.zip (as before)
        # - on success: patched_success.zip
        try:
            if cli.mode in ("workspace", "finalize", "finalize_workspace") and (
                not policy.test_mode
            ):
                issue_id = cli.issue_id or "unknown"

                archived_path: Path | None = used_patch_for_zip if cli.mode == "workspace" else None

                # Post-success audit (if enabled by workflow). If audit fails, treat as failure and
                # produce diagnostics archive instead of success archive.
                if exit_code == 0 and push_ok_for_posthook is True:
                    try:
                        _run_post_success_audit(logger, repo_root, policy)
                    except Exception as _audit_e:
                        exit_code = 1
                        logger.section("AUDIT")
                        logger.line(f"post_success_audit_failed={_audit_e!r}")
                if cli.mode == "workspace":
                    if exit_code == 0:
                        # Best effort: if caller returned success before archiving, archive now.
                        if (
                            archived_path is None
                            and patch_script is not None
                            and patch_script.exists()
                        ):
                            archived_path = archive_patch(
                                logger, patch_script, paths.successful_dir
                            )
                    else:
                        # Failure: archive the exact patch script selected for this run into
                        # unsuccessful/.
                        ps: Path | None = None
                        if patch_script is not None:
                            ps = patch_script
                        else:
                            if cli.patch_script:
                                raw = Path(cli.patch_script)
                                if raw.is_absolute():
                                    ps = raw
                                else:
                                    cand_repo = (repo_root / raw).resolve()
                                    cand_patchdir = (paths.patch_dir / raw).resolve()
                                    ps = cand_repo if cand_repo.exists() else cand_patchdir
                            else:
                                ps = (paths.patch_dir / f"issue_{issue_id}.py").resolve()

                        candidates: list[Path] = []
                        if ps is not None:
                            candidates.append(ps)
                            candidates.append((paths.patch_dir / ps.name).resolve())

                        seen: set[str] = set()
                        uniq: list[Path] = []
                        for c in candidates:
                            k = str(c)
                            if k not in seen:
                                seen.add(k)
                                uniq.append(c)

                        for c in uniq:
                            if c.exists():
                                archived_path = archive_patch(logger, c, paths.unsuccessful_dir)
                                break

                        if archived_path is None:
                            logger.section("ARCHIVE PATCH")
                            logger.line(f"no patch script found to archive; tried: {uniq}")

                # Post-success audit (if enabled by workflow). If audit fails, treat as failure and
                # produce diagnostics archive instead of success archive.
                if exit_code == 0 and push_ok_for_posthook is True:
                    try:
                        _run_post_success_audit(logger, repo_root, policy)
                    except Exception as _audit_e:
                        exit_code = 1
                        logger.section("AUDIT")
                        logger.line(f"post_success_audit_failed={_audit_e!r}")
                if exit_code == 0:
                    # Success: create git-archive snapshot of final repo state (no log inside).
                    # Success: create git-archive snapshot of final repo state.
                    repo_name = repo_root.name
                    branch_name = git_ops.current_branch(logger, repo_root).strip()
                    if branch_name == "HEAD":
                        branch_name = "detached"

                    template = policy.success_archive_name
                    try:
                        rendered = template.format(repo=repo_name, branch=branch_name)
                    except Exception as e:
                        raise RunnerError(
                            "POSTHOOK",
                            "CONFIG",
                            f"invalid success_archive_name template: {template!r} ({e!r})",
                        ) from e

                    name = Path(rendered).name
                    if not name.lower().endswith(".zip"):
                        name = f"{name}.zip"
                    zip_path = paths.patch_dir / name
                    git_ops.git_archive(logger, repo_root, zip_path, treeish="HEAD")
                else:
                    # Failure: create diagnostics archive with log + subset of repo files.
                    zip_path = paths.patch_dir / "patched.zip"

                    include_patch_paths: list[Path] = []
                    include_patch_blobs: list[tuple[str, bytes]] = []

                    # Include patch script only when patching did not apply.
                    if (
                        not patch_applied_successfully
                        and archived_path is not None
                        and archived_path.exists()
                        and not unified_mode
                    ):
                        include_patch_paths.append(archived_path)

                    # Unified patch mode: include only failed .patch inputs (not the original zip).
                    for name, data in failed_patch_blobs_for_zip:
                        include_patch_blobs.append((name, data))

                    ws_repo = (
                        ws_for_posthook.repo
                        if ws_for_posthook is not None
                        else (paths.workspaces_dir / f"issue_{issue_id}" / "repo")
                    )

                    make_failure_zip(
                        logger,
                        zip_path,
                        workspace_repo=ws_repo,
                        log_path=log_path,
                        include_repo_files=files_for_fail_zip,
                        include_patch_blobs=include_patch_blobs,
                        include_patch_paths=include_patch_paths,
                    )
                # Deferred rollback after diagnostics archive.
                # Keeps workspace available for zip creation.
                if (
                    exit_code != 0
                    and rollback_ws_for_posthook is not None
                    and rollback_ckpt_for_posthook is not None
                    and getattr(policy, "rollback_workspace_on_fail", False)
                ):
                    rollback_to_checkpoint(
                        logger,
                        rollback_ws_for_posthook.repo,
                        rollback_ckpt_for_posthook,
                    )

                if (
                    exit_code == 0
                    and delete_workspace_after_archive
                    and ws_for_posthook is not None
                ):
                    delete_workspace(logger, ws_for_posthook)
        except Exception as _e:
            try:
                logger.section("POSTHOOK-ERROR")
                logger.line(repr(_e))
            except Exception:
                pass

        if cli.mode == "workspace" and policy.test_mode:
            try:
                logger.section("TEST MODE CLEANUP")
                if ws_for_posthook is None:
                    logger.line("workspace_present=0")
                else:
                    logger.line("workspace_present=1")
                    logger.line(f"workspace_root={ws_for_posthook.root}")
                    logger.line("workspace_delete=1")
                    delete_workspace(logger, ws_for_posthook)
            except Exception as _e2:
                try:
                    logger.section("TEST_MODE_CLEANUP_ERROR")
                    logger.line(repr(_e2))
                except Exception:
                    pass

        with suppress(Exception):
            lock.release()
        logger.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
