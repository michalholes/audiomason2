from __future__ import annotations

import os
import shutil
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from am_patch import git_ops, runtime
from am_patch.archive import archive_patch
from am_patch.artifacts import build_artifacts
from am_patch.audit_rubric_check import check_audit_rubric_coverage
from am_patch.cli import parse_args
from am_patch.config import (
    Policy,
    apply_cli_overrides,
    build_policy,
    load_config,
    policy_for_log,
    resolve_config_path,
)
from am_patch.errors import RunnerError, fingerprint
from am_patch.execution_context import open_execution_context
from am_patch.failure_zip import cleanup_on_success_commit as cleanup_failure_zips_on_success
from am_patch.fs_junk import fs_junk_ignore_partition
from am_patch.gates import run_badguys, run_gates
from am_patch.lock import FileLock
from am_patch.log import Logger, new_log_file
from am_patch.patch_archive_select import select_latest_issue_patch
from am_patch.patch_exec import run_patch, run_unified_patch_bundle
from am_patch.patch_input import resolve_patch_plan
from am_patch.paths import default_paths, ensure_dirs
from am_patch.post_success_audit import run_post_success_audit
from am_patch.promote import promote_files
from am_patch.repo_root import is_under, resolve_repo_root
from am_patch.runtime import (
    _gate_progress,
    _maybe_run_badguys,
    _parse_gate_list,
    _stage_do,
    _stage_fail,
    _stage_ok,
    _stage_rank,
    _under_targets,
)
from am_patch.scope import blessed_gate_outputs_in, changed_paths, enforce_scope_delta
from am_patch.state import save_state, update_union
from am_patch.status import StatusReporter
from am_patch.validation import run_validation
from am_patch.version import RUNNER_VERSION
from am_patch.workspace import (
    delete_workspace,
    drop_checkpoint,
    open_existing_workspace,
    rollback_to_checkpoint,
)
from am_patch.workspace_history import (
    workspace_history_dirs,
    workspace_store_current_patch,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]


@dataclass
class RunContext:
    cli: Any
    policy: Policy
    config_path: Path
    used_cfg: str
    repo_root: Path
    patch_root: Path
    patch_dir: Path
    isolated_work_patch_dir: Path | None
    paths: Any
    log_path: Path
    json_path: Path | None
    logger: Logger
    status: StatusReporter
    verbosity: str
    log_level: str


def _fs_junk_ignore_partition(
    paths: list[str],
    *,
    ignore_prefixes: tuple[str, ...] | list[str],
    ignore_suffixes: tuple[str, ...] | list[str],
    ignore_contains: tuple[str, ...] | list[str],
) -> tuple[list[str], list[str]]:
    return fs_junk_ignore_partition(
        paths,
        ignore_prefixes=ignore_prefixes,
        ignore_suffixes=ignore_suffixes,
        ignore_contains=ignore_contains,
    )


def _run_post_success_audit(logger: Logger, repo_root: Path, policy: Policy) -> None:
    return run_post_success_audit(logger, repo_root, policy)


def _resolve_repo_root() -> Path:
    return resolve_repo_root()


def _is_under(child: Path, parent: Path) -> bool:
    return is_under(child, parent)


def _select_latest_issue_patch(*, patch_dir: Path, issue_id: str, hint_name: str | None) -> Path:
    return select_latest_issue_patch(patch_dir=patch_dir, issue_id=issue_id, hint_name=hint_name)


def _workspace_history_dirs(
    ws_root: Path,
    *,
    history_logs_dir: str = "logs",
    history_oldlogs_dir: str = "oldlogs",
    history_patches_dir: str = "patches",
    history_oldpatches_dir: str = "oldpatches",
) -> tuple[Path, Path, Path, Path]:
    return workspace_history_dirs(
        ws_root,
        history_logs_dir=history_logs_dir,
        history_oldlogs_dir=history_oldlogs_dir,
        history_patches_dir=history_patches_dir,
        history_oldpatches_dir=history_oldpatches_dir,
    )


def _workspace_store_current_patch(
    ws,
    patch_script: Path,
    *,
    history_logs_dir: str,
    history_oldlogs_dir: str,
    history_patches_dir: str,
    history_oldpatches_dir: str,
) -> None:
    return workspace_store_current_patch(
        ws,
        patch_script,
        history_logs_dir=history_logs_dir,
        history_oldlogs_dir=history_oldlogs_dir,
        history_patches_dir=history_patches_dir,
        history_oldpatches_dir=history_oldpatches_dir,
    )


def build_effective_policy(argv: list[str]) -> int | tuple[Any, Policy, Path, str]:
    cli = parse_args(argv)

    defaults = Policy()
    config_path = resolve_config_path(cli.config_path, _REPO_ROOT, _SCRIPTS_DIR)
    cfg, used_cfg = load_config(config_path)
    policy = build_policy(defaults, cfg)

    apply_cli_overrides(
        policy,
        {
            "run_all_tests": cli.run_all_tests,
            "verbosity": getattr(cli, "verbosity", None),
            "log_level": getattr(cli, "log_level", None),
            "json_out": getattr(cli, "json_out", None),
            "console_color": getattr(cli, "console_color", None),
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
            "gates_skip_js": getattr(cli, "skip_js", None),
            "gates_skip_docs": getattr(cli, "skip_docs", None),
            "gates_skip_monolith": getattr(cli, "skip_monolith", None),
            "gates_on_partial_apply": getattr(cli, "gates_on_partial_apply", None),
            "gates_on_zero_apply": getattr(cli, "gates_on_zero_apply", None),
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
            "gate_docs_include": (
                []
                if (
                    getattr(cli, "docs_include", None) is not None
                    and str(cli.docs_include).strip() == ""
                )
                else ([s.strip() for s in str(cli.docs_include).split(",") if s.strip()])
                if getattr(cli, "docs_include", None) is not None
                else None
            ),
            "gate_docs_exclude": (
                []
                if (
                    getattr(cli, "docs_exclude", None) is not None
                    and str(cli.docs_exclude).strip() == ""
                )
                else ([s.strip() for s in str(cli.docs_exclude).split(",") if s.strip()])
                if getattr(cli, "docs_exclude", None) is not None
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
        raise SystemExit(0)

    if policy.test_mode and cli.mode != "workspace":
        raise SystemExit("test-mode is supported only in workspace mode")

    return cli, policy, Path(config_path), str(used_cfg)


def build_paths_and_logger(
    cli: Any, policy: Policy, config_path: Path, used_cfg: str
) -> RunContext:
    repo_root = Path(policy.repo_root) if policy.repo_root else _resolve_repo_root()
    patch_root = Path(policy.patch_dir) if policy.patch_dir else (repo_root / policy.patch_dir_name)
    isolated_work_patch_dir: Path | None = None
    patch_dir = patch_root
    if (
        policy.test_mode
        and getattr(policy, "test_mode_isolate_patch_dir", True)
        and policy.patch_dir is None
        and cli.issue_id is not None
    ):
        isolated_work_patch_dir = (
            patch_root / "_test_mode" / f"issue_{cli.issue_id}_pid_{os.getpid()}"
        )
        patch_dir = isolated_work_patch_dir
    paths = default_paths(
        repo_root=repo_root,
        patch_dir=patch_root,
        logs_dir_name=policy.patch_layout_logs_dir,
        json_dir_name=policy.patch_layout_json_dir,
        workspaces_dir_name=policy.patch_layout_workspaces_dir,
        successful_dir_name=policy.patch_layout_successful_dir,
        unsuccessful_dir_name=policy.patch_layout_unsuccessful_dir,
        lockfile_name=policy.lockfile_name,
        current_log_symlink_name=policy.current_log_symlink_name,
    )
    ensure_dirs(paths)

    log_path = new_log_file(
        paths.logs_dir,
        issue_id=cli.issue_id,
        ts_format=policy.log_ts_format,
        issue_template=policy.log_template_issue,
        finalize_template=policy.log_template_finalize,
    )
    verbosity = getattr(policy, "verbosity", "verbose")
    log_level = getattr(policy, "log_level", "verbose")
    status = StatusReporter(enabled=(verbosity != "quiet"))
    json_path: Path | None = None
    if getattr(policy, "json_out", False):
        if cli.issue_id is not None:
            json_name = f"am_patch_issue_{cli.issue_id}.jsonl"
        else:
            json_name = "am_patch_finalize.jsonl"
        json_path = paths.json_dir / json_name

    logger = Logger(
        log_path=log_path,
        symlink_path=paths.symlink_path,
        screen_level=verbosity,
        log_level=log_level,
        console_color=getattr(policy, "console_color", "auto"),
        symlink_enabled=policy.current_log_symlink_enabled,
        symlink_target_rel=Path(policy.patch_layout_logs_dir) / log_path.name,
        json_enabled=getattr(policy, "json_out", False),
        json_path=json_path,
        stage_provider=status.get_stage,
    )

    logger.emit(
        severity="INFO",
        channel="CORE",
        message=(
            f"START: issue={cli.issue_id or '(none)'} mode={cli.mode} "
            f"verbosity={verbosity} log_level={log_level}\n"
        ),
        summary=True,
        kind="START",
    )
    logger.emit_json_hello(
        issue_id=cli.issue_id, mode=cli.mode, verbosity=verbosity, log_level=log_level
    )

    status.start()

    runtime.status = status
    runtime.logger = logger
    runtime.policy = policy
    runtime.repo_root = repo_root
    runtime.paths = paths
    runtime.cli = cli
    runtime.run_badguys = run_badguys
    runtime.RunnerError = RunnerError

    return RunContext(
        cli=cli,
        policy=policy,
        config_path=config_path,
        used_cfg=str(used_cfg),
        repo_root=repo_root,
        patch_root=patch_root,
        patch_dir=patch_dir,
        isolated_work_patch_dir=isolated_work_patch_dir,
        paths=paths,
        log_path=log_path,
        json_path=json_path,
        logger=logger,
        status=status,
        verbosity=verbosity,
        log_level=log_level,
    )


def run_mode(ctx: RunContext) -> dict[str, Any]:
    cli = ctx.cli
    policy = ctx.policy
    repo_root = ctx.repo_root
    patch_root = ctx.patch_root
    patch_dir = ctx.patch_dir
    config_path = ctx.config_path
    used_cfg = ctx.used_cfg
    paths = ctx.paths
    log_path = ctx.log_path
    logger = ctx.logger

    def _result(exit_code: int) -> dict[str, Any]:
        return {
            "lock": lock,
            "exit_code": exit_code,
            "unified_mode": unified_mode,
            "patch_script": patch_script,
            "used_patch_for_zip": used_patch_for_zip,
            "files_for_fail_zip": files_for_fail_zip,
            "failed_patch_blobs_for_zip": failed_patch_blobs_for_zip,
            "patch_applied_successfully": patch_applied_successfully,
            "applied_ok_count": applied_ok_count,
            "rollback_ckpt_for_posthook": rollback_ckpt_for_posthook,
            "rollback_ws_for_posthook": rollback_ws_for_posthook,
            "issue_diff_base_sha": issue_diff_base_sha,
            "issue_diff_paths": issue_diff_paths,
            "delete_workspace_after_archive": delete_workspace_after_archive,
            "ws_for_posthook": ws_for_posthook,
            "push_ok_for_posthook": push_ok_for_posthook,
            "final_commit_sha": final_commit_sha,
            "final_pushed_files": final_pushed_files,
            "final_fail_stage": final_fail_stage,
            "final_fail_reason": final_fail_reason,
            "primary_fail_stage": primary_fail_stage,
            "primary_fail_reason": primary_fail_reason,
            "secondary_failures": secondary_failures,
        }

    lock = FileLock(paths.lock_path)
    unified_mode: bool = False
    patch_script: Path | None = None
    commit_sha: str | None = None
    push_ok: bool | None = None
    used_patch_for_zip: Path | None = None
    files_for_fail_zip: list[str] = []
    failed_patch_blobs_for_zip: list[tuple[str, bytes]] = []
    patch_applied_successfully: bool = False
    applied_ok_count: int = 0
    rollback_ckpt_for_posthook = None
    rollback_ws_for_posthook = None
    issue_diff_base_sha: str | None = None
    issue_diff_paths: list[str] = []

    delete_workspace_after_archive: bool = False
    ws_for_posthook = None
    push_ok_for_posthook: bool | None = None
    final_commit_sha: str | None = None
    final_pushed_files: list[str] | None = None
    final_fail_stage: str | None = None
    final_fail_reason: str | None = None
    primary_fail_stage: str | None = None
    primary_fail_reason: str | None = None
    secondary_failures: list[tuple[str, str]] = []
    try:
        logger.section("AM_PATCH START")
        logger.line(f"RUNNER_VERSION={RUNNER_VERSION}")
        logger.line(f"repo_root={repo_root}")
        logger.line(f"patch_dir={patch_dir}")
        if patch_dir != patch_root:
            logger.line(f"patch_root={patch_root}")
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

            ws = open_existing_workspace(
                logger,
                paths.workspaces_dir,
                issue_id,
                issue_dir_template=policy.workspace_issue_dir_template,
                repo_dir_name=policy.workspace_repo_dir_name,
                meta_filename=policy.workspace_meta_filename,
            )
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

            decision_paths_ws = changed_paths(logger, ws.repo)

            # Failure archive hint: include current workspace changes (even in -w) so
            # patched.zip is reproducible if gates fail.
            files_for_fail_zip = sorted(set(files_for_fail_zip) | set(decision_paths_ws))

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
                skip_js=policy.gates_skip_js,
                skip_pytest=policy.gates_skip_pytest,
                skip_mypy=policy.gates_skip_mypy,
                skip_docs=policy.gates_skip_docs,
                skip_monolith=policy.gates_skip_monolith,
                gate_monolith_enabled=policy.gate_monolith_enabled,
                gate_monolith_mode=policy.gate_monolith_mode,
                gate_monolith_scan_scope=policy.gate_monolith_scan_scope,
                gate_monolith_compute_fanin=policy.gate_monolith_compute_fanin,
                gate_monolith_on_parse_error=policy.gate_monolith_on_parse_error,
                gate_monolith_areas=policy.gate_monolith_areas,
                gate_monolith_large_loc=policy.gate_monolith_large_loc,
                gate_monolith_huge_loc=policy.gate_monolith_huge_loc,
                gate_monolith_large_allow_loc_increase=policy.gate_monolith_large_allow_loc_increase,
                gate_monolith_huge_allow_loc_increase=policy.gate_monolith_huge_allow_loc_increase,
                gate_monolith_large_allow_exports_delta=policy.gate_monolith_large_allow_exports_delta,
                gate_monolith_huge_allow_exports_delta=policy.gate_monolith_huge_allow_exports_delta,
                gate_monolith_large_allow_imports_delta=policy.gate_monolith_large_allow_imports_delta,
                gate_monolith_huge_allow_imports_delta=policy.gate_monolith_huge_allow_imports_delta,
                gate_monolith_new_file_max_loc=policy.gate_monolith_new_file_max_loc,
                gate_monolith_new_file_max_exports=policy.gate_monolith_new_file_max_exports,
                gate_monolith_new_file_max_imports=policy.gate_monolith_new_file_max_imports,
                gate_monolith_hub_fanin_delta=policy.gate_monolith_hub_fanin_delta,
                gate_monolith_hub_fanout_delta=policy.gate_monolith_hub_fanout_delta,
                gate_monolith_hub_exports_delta_min=policy.gate_monolith_hub_exports_delta_min,
                gate_monolith_hub_loc_delta_min=policy.gate_monolith_hub_loc_delta_min,
                gate_monolith_crossarea_min_distinct_areas=policy.gate_monolith_crossarea_min_distinct_areas,
                gate_monolith_catchall_basenames=policy.gate_monolith_catchall_basenames,
                gate_monolith_catchall_dirs=policy.gate_monolith_catchall_dirs,
                gate_monolith_catchall_allowlist=policy.gate_monolith_catchall_allowlist,
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
                decision_paths=decision_paths_ws,
                progress=_gate_progress,
            )

            # Gates can modify files (e.g. ruff format/autofix). Refresh the failure
            # archive subset after workspace gates.
            changed_after_ws_gates = changed_paths(logger, ws.repo)
            files_for_fail_zip = sorted(set(files_for_fail_zip) | set(changed_after_ws_gates))

            _maybe_run_badguys(cwd=ws.repo, decision_paths=decision_paths_ws)

            changed_all = changed_paths(logger, ws.repo)
            promote_list, ignored = _fs_junk_ignore_partition(
                changed_all,
                ignore_prefixes=policy.scope_ignore_prefixes,
                ignore_suffixes=policy.scope_ignore_suffixes,
                ignore_contains=policy.scope_ignore_contains,
            )
            logger.section("PROMOTION PLAN")
            logger.line(f"changed_all={changed_all}")
            logger.line(f"ignored_paths={ignored}")
            logger.line(f"files_to_promote={promote_list}")

            issue_diff_base_sha = ws.base_sha
            issue_diff_paths = list(promote_list)

            if not promote_list:
                raise RunnerError("PREFLIGHT", "WORKSPACE", "no promotable workspace changes")

            # If later steps (promotion or live gates) fail, ensure the failure zip
            # includes the exact files that were planned for promotion.
            files_for_fail_zip = sorted(set(files_for_fail_zip) | set(promote_list))

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
            decision_paths_live = list(promote_list)
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
                skip_js=policy.gates_skip_js,
                skip_pytest=policy.gates_skip_pytest,
                skip_mypy=policy.gates_skip_mypy,
                skip_docs=policy.gates_skip_docs,
                skip_monolith=policy.gates_skip_monolith,
                gate_monolith_enabled=policy.gate_monolith_enabled,
                gate_monolith_mode=policy.gate_monolith_mode,
                gate_monolith_scan_scope=policy.gate_monolith_scan_scope,
                gate_monolith_compute_fanin=policy.gate_monolith_compute_fanin,
                gate_monolith_on_parse_error=policy.gate_monolith_on_parse_error,
                gate_monolith_areas=policy.gate_monolith_areas,
                gate_monolith_large_loc=policy.gate_monolith_large_loc,
                gate_monolith_huge_loc=policy.gate_monolith_huge_loc,
                gate_monolith_large_allow_loc_increase=policy.gate_monolith_large_allow_loc_increase,
                gate_monolith_huge_allow_loc_increase=policy.gate_monolith_huge_allow_loc_increase,
                gate_monolith_large_allow_exports_delta=policy.gate_monolith_large_allow_exports_delta,
                gate_monolith_huge_allow_exports_delta=policy.gate_monolith_huge_allow_exports_delta,
                gate_monolith_large_allow_imports_delta=policy.gate_monolith_large_allow_imports_delta,
                gate_monolith_huge_allow_imports_delta=policy.gate_monolith_huge_allow_imports_delta,
                gate_monolith_new_file_max_loc=policy.gate_monolith_new_file_max_loc,
                gate_monolith_new_file_max_exports=policy.gate_monolith_new_file_max_exports,
                gate_monolith_new_file_max_imports=policy.gate_monolith_new_file_max_imports,
                gate_monolith_hub_fanin_delta=policy.gate_monolith_hub_fanin_delta,
                gate_monolith_hub_fanout_delta=policy.gate_monolith_hub_fanout_delta,
                gate_monolith_hub_exports_delta_min=policy.gate_monolith_hub_exports_delta_min,
                gate_monolith_hub_loc_delta_min=policy.gate_monolith_hub_loc_delta_min,
                gate_monolith_crossarea_min_distinct_areas=policy.gate_monolith_crossarea_min_distinct_areas,
                gate_monolith_catchall_basenames=policy.gate_monolith_catchall_basenames,
                gate_monolith_catchall_dirs=policy.gate_monolith_catchall_dirs,
                gate_monolith_catchall_allowlist=policy.gate_monolith_catchall_allowlist,
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
                decision_paths=decision_paths_live,
                progress=_gate_progress,
            )
            _maybe_run_badguys(cwd=repo_root, decision_paths=decision_paths_live)
            if policy.commit_and_push:
                commit_sha = git_ops.commit(
                    logger,
                    repo_root,
                    str(ws.message),
                    stage_all=False,
                )
                push_ok = git_ops.push(
                    logger,
                    repo_root,
                    policy.default_branch,
                    allow_fail=policy.allow_push_fail,
                )
                final_commit_sha = commit_sha

                if commit_sha and cli.issue_id is not None:
                    cleanup_failure_zips_on_success(
                        patch_dir=paths.patch_dir,
                        policy=policy,
                        issue=str(cli.issue_id),
                    )

                if commit_sha and cli.issue_id is not None:
                    cleanup_failure_zips_on_success(
                        patch_dir=paths.patch_dir,
                        policy=policy,
                        issue=str(cli.issue_id),
                    )

                # Wire live results into the unified end-of-run summary.
                push_ok_for_posthook = push_ok
                if push_ok is True and commit_sha:
                    try:
                        ns = git_ops.commit_changed_files_name_status(
                            logger,
                            repo_root,
                            commit_sha,
                        )
                        final_pushed_files = [f"{st} {p}" for (st, p) in ns]
                    except Exception:
                        # Best-effort only; never override SUCCESS contract.
                        final_pushed_files = None

            logger.section("SUCCESS")
            if policy.commit_and_push:
                logger.line(f"commit_sha={commit_sha}")
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

            return _result(0)

        if cli.mode == "finalize":
            git_ops.fetch(logger, repo_root)
            if policy.require_up_to_date and not policy.skip_up_to_date:
                git_ops.require_up_to_date(logger, repo_root, policy.default_branch)
            if policy.enforce_main_branch and not policy.allow_non_main:
                git_ops.require_branch(logger, repo_root, policy.default_branch)

            issue_diff_base_sha = git_ops.head_sha(logger, repo_root)
            decision_paths_finalize = changed_paths(logger, repo_root)
            issue_diff_paths = list(decision_paths_finalize)

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
                skip_js=policy.gates_skip_js,
                skip_pytest=policy.gates_skip_pytest,
                skip_mypy=policy.gates_skip_mypy,
                skip_docs=policy.gates_skip_docs,
                skip_monolith=policy.gates_skip_monolith,
                gate_monolith_enabled=policy.gate_monolith_enabled,
                gate_monolith_mode=policy.gate_monolith_mode,
                gate_monolith_scan_scope=policy.gate_monolith_scan_scope,
                gate_monolith_compute_fanin=policy.gate_monolith_compute_fanin,
                gate_monolith_on_parse_error=policy.gate_monolith_on_parse_error,
                gate_monolith_areas=policy.gate_monolith_areas,
                gate_monolith_large_loc=policy.gate_monolith_large_loc,
                gate_monolith_huge_loc=policy.gate_monolith_huge_loc,
                gate_monolith_large_allow_loc_increase=policy.gate_monolith_large_allow_loc_increase,
                gate_monolith_huge_allow_loc_increase=policy.gate_monolith_huge_allow_loc_increase,
                gate_monolith_large_allow_exports_delta=policy.gate_monolith_large_allow_exports_delta,
                gate_monolith_huge_allow_exports_delta=policy.gate_monolith_huge_allow_exports_delta,
                gate_monolith_large_allow_imports_delta=policy.gate_monolith_large_allow_imports_delta,
                gate_monolith_huge_allow_imports_delta=policy.gate_monolith_huge_allow_imports_delta,
                gate_monolith_new_file_max_loc=policy.gate_monolith_new_file_max_loc,
                gate_monolith_new_file_max_exports=policy.gate_monolith_new_file_max_exports,
                gate_monolith_new_file_max_imports=policy.gate_monolith_new_file_max_imports,
                gate_monolith_hub_fanin_delta=policy.gate_monolith_hub_fanin_delta,
                gate_monolith_hub_fanout_delta=policy.gate_monolith_hub_fanout_delta,
                gate_monolith_hub_exports_delta_min=policy.gate_monolith_hub_exports_delta_min,
                gate_monolith_hub_loc_delta_min=policy.gate_monolith_hub_loc_delta_min,
                gate_monolith_crossarea_min_distinct_areas=policy.gate_monolith_crossarea_min_distinct_areas,
                gate_monolith_catchall_basenames=policy.gate_monolith_catchall_basenames,
                gate_monolith_catchall_dirs=policy.gate_monolith_catchall_dirs,
                gate_monolith_catchall_allowlist=policy.gate_monolith_catchall_allowlist,
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
                decision_paths=decision_paths_finalize,
                progress=_gate_progress,
            )

            changed_after_finalize_gates = changed_paths(logger, repo_root)
            issue_diff_paths = sorted(set(issue_diff_paths) | set(changed_after_finalize_gates))

            _maybe_run_badguys(cwd=repo_root, decision_paths=decision_paths_finalize)
            if policy.commit_and_push:
                commit_sha = git_ops.commit(logger, repo_root, cli.message or "finalize")
                push_ok = git_ops.push(
                    logger,
                    repo_root,
                    policy.default_branch,
                    allow_fail=policy.allow_push_fail,
                )
                final_commit_sha = commit_sha

            logger.section("SUCCESS")
            if policy.commit_and_push:
                logger.line(f"commit_sha={commit_sha}")
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

            # Wire finalize results into the unified end-of-run summary.
            push_ok_for_posthook = push_ok
            if push_ok is True and commit_sha:
                try:
                    ns = git_ops.commit_changed_files_name_status(
                        logger,
                        repo_root,
                        commit_sha,
                    )
                    final_pushed_files = [f"{st} {p}" for (st, p) in ns]
                except Exception:
                    # Best-effort only; never override SUCCESS contract.
                    final_pushed_files = None

            if push_ok is True:
                _run_post_success_audit(logger, repo_root, policy)
            return _result(0)

        issue_id = cli.issue_id
        assert issue_id is not None

        plan = resolve_patch_plan(
            logger=logger,
            cli=cli,
            policy=policy,
            issue_id=issue_id,
            repo_root=repo_root,
            patch_root=patch_root,
        )
        patch_script = plan.patch_script
        unified_mode = plan.unified_mode
        files_current = list(plan.files_declared)

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

        exec_ctx = open_execution_context(
            logger=logger,
            cli=cli,
            policy=policy,
            paths=paths,
            repo_root=repo_root,
            patch_script=patch_script,
            unified_mode=unified_mode,
            files_declared=files_current,
        )
        ws = exec_ctx.ws
        ws_for_posthook = ws
        _workspace_store_current_patch(
            ws,
            patch_script,
            history_logs_dir=policy.workspace_history_logs_dir,
            history_oldlogs_dir=policy.workspace_history_oldlogs_dir,
            history_patches_dir=policy.workspace_history_patches_dir,
            history_oldpatches_dir=policy.workspace_history_oldpatches_dir,
        )
        ckpt = exec_ctx.checkpoint
        before = exec_ctx.changed_before
        st = exec_ctx.state_before
        live_guard_before = exec_ctx.live_guard_before

        try:
            touched_for_zip: list[str] = []
            failed_patch_blobs: list[tuple[str, bytes]] = []
            patch_applied_any = False

            _stage_do("PATCH_APPLY")

            if unified_mode:
                res = run_unified_patch_bundle(
                    logger,
                    patch_script,
                    workspace_repo=ws.repo,
                    policy=policy,
                )
                patch_applied_any = res.applied_ok > 0
                applied_ok_count = res.applied_ok
                files_current = list(res.declared_files)
                touched_for_zip = list(res.touched_files)
                failed_patch_blobs = [(f.name, f.data) for f in res.failures]

                if res.failures:
                    primary_fail_stage = "PATCH"
                    primary_fail_reason = "patch apply failed"

                # For patched.zip on failure: always include touched targets and failed patch blobs.
                # This must be available even if scope enforcement fails later.
                files_for_fail_zip = sorted(set(touched_for_zip) | set(files_current))
                failed_patch_blobs_for_zip = list(failed_patch_blobs)
                patch_applied_successfully = patch_applied_any

            else:
                try:
                    run_patch(logger, patch_script, workspace_repo=ws.repo, policy=policy)
                    patch_applied_any = True
                    applied_ok_count = 1
                except RunnerError as e:
                    primary_fail_stage = "PATCH"
                    primary_fail_reason = e.message
                    patch_applied_any = False

            after = changed_paths(logger, ws.repo)
            if (not unified_mode) and (primary_fail_stage is not None):
                patch_applied_any = set(after) != set(before)
            touched: list[str] = []
            try:
                touched = enforce_scope_delta(
                    logger,
                    files_current=files_current,
                    before=before,
                    after=after,
                    no_op_fail=policy.no_op_fail,
                    allow_no_op=policy.allow_no_op,
                    allow_outside_files=policy.allow_outside_files,
                    allowed_union=st.allowed_union,
                    declared_untouched_fail=policy.declared_untouched_fail,
                    allow_declared_untouched=policy.allow_declared_untouched,
                    blessed_outputs=policy.blessed_gate_outputs,
                    ignore_prefixes=policy.scope_ignore_prefixes,
                    ignore_suffixes=policy.scope_ignore_suffixes,
                    ignore_contains=policy.scope_ignore_contains,
                )
            except RunnerError as _scope_e:
                if primary_fail_stage is None:
                    raise
                logger.section("SECONDARY FAILURE")
                logger.line(str(_scope_e))
                secondary_failures.append((str(_scope_e.stage), str(_scope_e.message)))

            if primary_fail_stage is None:
                _stage_ok("PATCH_APPLY")
            else:
                _stage_fail("PATCH_APPLY")

            # Snapshot dirty paths immediately after patch (before gates).
            dirty_after_patch = list(after)

            # For patched.zip on failure: include the cumulative issue allowed_union plus any known
            # patch targets and current dirty paths. This must be available even if scope
            # enforcement failed (e.g. patch apply failure followed by a scope secondary failure).
            fail_zip_files = set(st.allowed_union)
            fail_zip_files |= set(dirty_after_patch)
            fail_zip_files |= set(files_current)
            fail_zip_files |= set(touched)
            fail_zip_files |= set(touched_for_zip)
            files_for_fail_zip = sorted(fail_zip_files)
            failed_patch_blobs_for_zip = list(failed_patch_blobs)
            patch_applied_successfully = patch_applied_any

        except Exception:
            _stage_fail("PATCH_APPLY")
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

        defer_patch_apply_failure = False
        if primary_fail_stage is not None:
            if secondary_failures:
                logger.section("SECONDARY FAILURES (summary)")
                for stg, msg in secondary_failures:
                    logger.line(f"{stg}: {msg}")

            should_run_gates = (patch_applied_any and policy.gates_on_partial_apply) or (
                (not patch_applied_any) and policy.gates_on_zero_apply
            )
            if not should_run_gates:
                # Defer rollback until after diagnostics archive is created.
                rollback_ckpt_for_posthook = ckpt
                rollback_ws_for_posthook = ws
                raise RunnerError(
                    "PATCH", "PATCH_APPLY", primary_fail_reason or "patch apply failed"
                )

            # Apply failed but gates were explicitly requested by policy.
            # Emit exactly one line (screen-visible only at verbose/debug).
            logger.line("continuing_to_workspace_gates_due_to_patch_apply_failure_policy")
            defer_patch_apply_failure = True

        # Gates in workspace (NO rollback)
        run_validation(
            logger=logger,
            repo_root=repo_root,
            cwd=ws.repo,
            paths=paths,
            policy=policy,
            cli_mode=cli.mode,
            issue_id=cli.issue_id,
            decision_paths=touched,
            progress=_gate_progress,
            run_badguys_gate=True,
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
            return _result(0)

        # Determine what to promote/commit: all current dirty paths within allowed_union.
        dirty_all = changed_paths(logger, ws.repo)

        # Ruff autofix may introduce additional changes after the patch. When enabled,
        # automatically legalize ruff-only changes outside FILES (bounded to ruff_targets).
        if policy.ruff_autofix and getattr(policy, "ruff_autofix_legalize_outside", True):
            patch_set = set(dirty_after_patch)
            now_set = set(dirty_all)
            ruff_only = sorted(p for p in (now_set - patch_set) if p)
            if ruff_only:
                legalized = sorted([p for p in ruff_only if _under_targets(p)])
                if legalized:
                    st = update_union(st, legalized)
                    save_state(ws.root, st)
                    logger.line(f"legalized_ruff_autofix_files={legalized}")
        if defer_patch_apply_failure:
            # Ensure failure archive includes any gate-induced changes.
            files_for_fail_zip = sorted(set(files_for_fail_zip) | set(dirty_all))
            # Defer rollback until after diagnostics archive is created.
            rollback_ckpt_for_posthook = ckpt
            rollback_ws_for_posthook = ws
            raise RunnerError("PATCH", "PATCH_APPLY", primary_fail_reason or "patch apply failed")

        allowed_union = set(st.allowed_union)
        dirty_allowed = [p for p in dirty_all if p in allowed_union]
        dirty_blessed = blessed_gate_outputs_in(
            dirty_all, blessed_outputs=policy.blessed_gate_outputs
        )
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

        # Issue diff bundle context (used by posthook to build patches/artifacts).
        issue_diff_base_sha = ws.base_sha
        issue_diff_paths = list(to_promote)

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

        decision_paths_post_promote = list(to_promote)
        _maybe_run_badguys(cwd=repo_root, decision_paths=decision_paths_post_promote)

        if policy.commit_and_push:
            commit_sha = git_ops.commit(
                logger,
                repo_root,
                (ws.message or f"Issue {issue_id}: apply patch"),
                stage_all=False,
            )
            final_commit_sha = commit_sha

            if commit_sha and issue_id is not None:
                cleanup_failure_zips_on_success(
                    patch_dir=paths.patch_dir,
                    policy=policy,
                    issue=str(issue_id),
                )
            push_ok = git_ops.push(
                logger, repo_root, policy.default_branch, allow_fail=policy.allow_push_fail
            )

            if push_ok is True and commit_sha:
                try:
                    ns = git_ops.commit_changed_files_name_status(
                        logger,
                        repo_root,
                        commit_sha,
                    )
                    final_pushed_files = [f"{st} {p}" for (st, p) in ns]
                except Exception:
                    # Best-effort only; never override SUCCESS contract.
                    final_pushed_files = None

        push_ok_for_posthook = push_ok

        used_patch_for_zip = archive_patch(logger, patch_script, paths.successful_dir)

        drop_checkpoint(logger, ws.repo, ckpt)

        delete_workspace_after_archive = bool(policy.delete_workspace_on_success)

        logger.section("SUCCESS")
        if policy.commit_and_push:
            logger.line(f"commit_sha={commit_sha}")
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
            logger.line("commit_sha=SKIPPED")
            logger.line("push=SKIPPED")
        return _result(0)

    except RunnerError as e:
        logger.section("FAILURE")
        logger.line(str(e))
        logger.line(fingerprint(e))

        # Contract: map internal error to stable STAGE/REASON for final summary.
        # STAGE may be a comma-separated list of stage identifiers when multiple failures occur.
        final_fail_stage = str(e.stage)
        final_fail_reason = str(e.message)

        # Accumulate all known failures for final on-screen summary.
        stages: list[str] = []

        # Patch apply is a primary failure even if gates failed later (partial apply diagnostics).
        if primary_fail_stage is not None and primary_fail_stage == "PATCH":
            stages.append("PATCH_APPLY")

        # Secondary failures (e.g., scope after patch failure).
        for stg, _msg in secondary_failures:
            if stg == "PROMOTION":
                stages.append("PROMOTE")
            elif stg == "SCOPE":
                stages.append("SCOPE")
            elif stg:
                stages.append(stg)

        # Primary exception mapping.
        if e.stage == "GATES":
            msg = str(e.message)
            gates = _parse_gate_list(msg)
            for g in gates:
                stages.append(f"GATE_{g.upper()}")
            if not gates:
                stages.append("GATES")
            # Preserve existing reason mapping; keep it concise.
            final_fail_reason = "gates failed"
        elif e.stage == "PATCH":
            stages.append("PATCH_APPLY")
            final_fail_reason = "patch apply failed"
        elif e.stage == "PREFLIGHT":
            stages.append("PREFLIGHT")
            final_fail_reason = "invalid inputs"
        elif e.stage == "PROMOTION":
            stages.append("PROMOTE")
            final_fail_reason = "promotion failed"
        elif e.stage == "SCOPE":
            stages.append("SCOPE")
            final_fail_reason = "scope failed"
        else:
            stages.append(str(e.stage))

        # De-duplicate and sort deterministically.
        uniq: list[str] = []
        for s in stages:
            if s and s not in uniq:
                uniq.append(s)
        uniq.sort(key=lambda s: (_stage_rank(s), s))
        final_fail_stage = ", ".join(uniq) if uniq else (final_fail_stage or "INTERNAL")

        return _result(1)


def finalize_and_report(ctx: RunContext, result: dict[str, Any]) -> int:
    cli = ctx.cli
    policy = ctx.policy
    repo_root = ctx.repo_root
    paths = ctx.paths
    log_path = ctx.log_path
    logger = ctx.logger
    status = ctx.status
    verbosity = ctx.verbosity
    log_level = ctx.log_level
    json_path = ctx.json_path
    isolated_work_patch_dir = ctx.isolated_work_patch_dir

    # Bring mode locals into scope exactly as in the legacy main().
    lock = result.get("lock")
    exit_code = int(result.get("exit_code", 1))
    unified_mode = bool(result.get("unified_mode", False))
    patch_script = result.get("patch_script")
    used_patch_for_zip = result.get("used_patch_for_zip")

    files_for_fail_zip_raw = result.get("files_for_fail_zip")
    files_for_fail_zip: list[str] = (
        list(files_for_fail_zip_raw) if isinstance(files_for_fail_zip_raw, list) else []
    )

    failed_patch_blobs_raw = result.get("failed_patch_blobs_for_zip")
    failed_patch_blobs_for_zip: list[tuple[str, bytes]] = (
        list(failed_patch_blobs_raw) if isinstance(failed_patch_blobs_raw, list) else []
    )
    patch_applied_successfully = bool(result.get("patch_applied_successfully", False))
    applied_ok_count = int(result.get("applied_ok_count", 0))
    rollback_ckpt_for_posthook = result.get("rollback_ckpt_for_posthook")
    rollback_ws_for_posthook = result.get("rollback_ws_for_posthook")
    issue_diff_base_sha = result.get("issue_diff_base_sha")
    issue_diff_paths_raw = result.get("issue_diff_paths")
    issue_diff_paths: list[str] = (
        list(issue_diff_paths_raw) if isinstance(issue_diff_paths_raw, list) else []
    )
    delete_workspace_after_archive = bool(result.get("delete_workspace_after_archive", False))
    ws_for_posthook = result.get("ws_for_posthook")
    push_ok_for_posthook = result.get("push_ok_for_posthook")
    final_commit_sha = result.get("final_commit_sha")
    final_pushed_files = result.get("final_pushed_files")
    final_fail_stage = result.get("final_fail_stage")
    final_fail_reason = result.get("final_fail_reason")

    # Posthook: always create an archive after a workspace-mode run.
    # - on failure: patched.zip (as before)
    # - on success: patched_success.zip
    try:
        if cli.mode in ("workspace", "finalize", "finalize_workspace") and (not policy.test_mode):
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
                    if archived_path is None and patch_script is not None and patch_script.exists():
                        archived_path = archive_patch(logger, patch_script, paths.successful_dir)
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
            ws_repo = (
                ws_for_posthook.repo
                if ws_for_posthook is not None
                else (paths.workspaces_dir / f"issue_{issue_id}" / "repo")
            )

            build_artifacts(
                logger=logger,
                cli=cli,
                policy=policy,
                paths=paths,
                repo_root=repo_root,
                log_path=log_path,
                exit_code=exit_code,
                unified_mode=unified_mode,
                patch_applied_successfully=patch_applied_successfully,
                archived_patch=archived_path,
                failed_patch_blobs_for_zip=failed_patch_blobs_for_zip,
                files_for_fail_zip=files_for_fail_zip,
                ws_repo_for_fail_zip=ws_repo,
                ws_attempt=(ws_for_posthook.attempt if ws_for_posthook is not None else None),
                issue_diff_base_sha=issue_diff_base_sha,
                issue_diff_paths=issue_diff_paths,
            )
            # Deferred rollback after diagnostics archive.
            # Keeps workspace available for zip creation.
            if (
                exit_code != 0
                and rollback_ws_for_posthook is not None
                and rollback_ckpt_for_posthook is not None
            ):
                mode = getattr(policy, "rollback_workspace_on_fail", "none-applied")
                do_rb = False
                if mode == "never":
                    do_rb = False
                elif mode == "always":
                    do_rb = True
                else:  # none-applied (default)
                    do_rb = applied_ok_count == 0

                if do_rb:
                    logger.line(f"ROLLBACK: executed (mode={mode} applied_ok={applied_ok_count})")
                    rollback_to_checkpoint(
                        logger,
                        rollback_ws_for_posthook.repo,
                        rollback_ckpt_for_posthook,
                    )
                else:
                    logger.line(f"ROLLBACK: skipped (mode={mode} applied_ok={applied_ok_count})")

            if exit_code == 0 and delete_workspace_after_archive and ws_for_posthook is not None:
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
        status.stop()
    with suppress(Exception):
        if lock is not None:
            lock.release()

    # Final summary must always be present in the log file (even at log_level=quiet).
    try:
        screen_quiet = str(verbosity or "").strip().lower() == "quiet"
        log_quiet = str(log_level or "").strip().lower() == "quiet"
        logger.emit_json_result(
            ok=(exit_code == 0), return_code=exit_code, log_path=log_path, json_path=json_path
        )
        if exit_code == 0:
            logger.emit(
                severity="INFO",
                channel="CORE",
                message="RESULT: SUCCESS\n",
                kind="RESULT",
                summary=True,
                to_screen=True,
            )
            if push_ok_for_posthook is True and final_pushed_files is not None:
                logger.emit(
                    severity="INFO",
                    channel="CORE",
                    message="FILES:\n\n",
                    kind="FILES",
                    summary=True,
                    to_screen=not screen_quiet,
                    to_log=not log_quiet,
                )
                for line in final_pushed_files:
                    logger.emit(
                        severity="INFO",
                        channel="CORE",
                        message=f"{line}\n",
                        summary=True,
                        to_screen=not screen_quiet,
                        to_log=not log_quiet,
                    )
            logger.emit(
                severity="INFO",
                channel="CORE",
                message=f"COMMIT: {final_commit_sha or '(none)'}\n",
                kind="COMMIT",
                summary=True,
                to_screen=not screen_quiet,
                to_log=not log_quiet,
            )
            if policy.commit_and_push:
                if push_ok_for_posthook is True:
                    push_txt = "OK"
                elif push_ok_for_posthook is False:
                    push_txt = "FAIL"
                else:
                    push_txt = "UNKNOWN"
                logger.emit(
                    severity="INFO",
                    channel="CORE",
                    message=f"PUSH: {push_txt}\n",
                    kind="PUSH",
                    summary=True,
                    to_screen=not screen_quiet,
                    to_log=not log_quiet,
                )
            logger.emit(
                severity="INFO",
                channel="CORE",
                message=f"LOG: {log_path}\n",
                kind="TEXT",
                summary=True,
                to_screen=not screen_quiet,
                to_log=not log_quiet,
            )
        else:
            logger.emit(
                severity="INFO",
                channel="CORE",
                message="RESULT: FAIL\n",
                kind="RESULT",
                summary=True,
                to_screen=True,
            )
            stage = final_fail_stage or "INTERNAL"
            reason = final_fail_reason or "unexpected error"
            logger.emit(
                severity="INFO",
                channel="CORE",
                message=f"STAGE: {stage}\n",
                kind="STAGE",
                summary=True,
                to_screen=not screen_quiet,
                to_log=not log_quiet,
            )
            logger.emit(
                severity="INFO",
                channel="CORE",
                message=f"REASON: {reason}\n",
                kind="REASON",
                summary=True,
                to_screen=not screen_quiet,
                to_log=not log_quiet,
            )
            logger.emit(
                severity="INFO",
                channel="CORE",
                message=f"LOG: {log_path}\n",
                kind="TEXT",
                summary=True,
                to_screen=not screen_quiet,
                to_log=not log_quiet,
            )
    except Exception:
        pass

    logger.close()

    if policy.test_mode and isolated_work_patch_dir is not None:
        with suppress(Exception):
            shutil.rmtree(isolated_work_patch_dir, ignore_errors=True)

    return exit_code
