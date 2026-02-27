from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from am_patch import git_ops
from am_patch.errors import RunnerError, fingerprint
from am_patch.failure_zip import cleanup_on_success_commit as cleanup_failure_zips_on_success
from am_patch.gates import run_gates
from am_patch.paths import _fs_junk_ignore_partition
from am_patch.post_success_audit import run_post_success_audit
from am_patch.promote import promote_files
from am_patch.runtime import (
    _gate_progress,
    _maybe_run_badguys,
    _parse_gate_list,
    _stage_rank,
)
from am_patch.scope import changed_paths
from am_patch.workspace import (
    bump_existing_workspace_attempt,
    delete_workspace,
    open_existing_workspace,
)

if TYPE_CHECKING:
    from am_patch.engine import RunContext


def run_finalize_workspace_mode(ctx: RunContext) -> dict[str, Any]:
    cli = ctx.cli
    policy = ctx.policy
    repo_root = ctx.repo_root
    paths = ctx.paths
    logger = ctx.logger

    lock = getattr(ctx, "lock", None)

    unified_mode: bool = False
    patch_script: Path | None = None
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
        issue_id = cli.issue_id
        assert issue_id is not None

        ws = open_existing_workspace(
            logger,
            paths.workspaces_dir,
            str(issue_id),
            issue_dir_template=policy.workspace_issue_dir_template,
            repo_dir_name=policy.workspace_repo_dir_name,
            meta_filename=policy.workspace_meta_filename,
        )
        ws_for_posthook = ws

        # Ensure {attempt} increments on each finalize-workspace run.
        ws.attempt = bump_existing_workspace_attempt(ws.meta_path)

        logger.section("FINALIZE WORKSPACE")
        logger.line(f"workspace_root={ws.root}")
        logger.line(f"workspace_repo={ws.repo}")
        logger.line(f"workspace_meta={ws.meta_path}")
        logger.line(f"workspace_base_sha={ws.base_sha}")
        logger.line(f"workspace_attempt={ws.attempt}")

        # Commit message is always sourced from workspace meta.json.
        if not ws.message or not str(ws.message).strip():
            raise RunnerError(
                "PREFLIGHT",
                "WORKSPACE",
                "workspace meta.json missing non-empty message",
            )

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
            gate_monolith_extensions=policy.gate_monolith_extensions,
            gate_monolith_compute_fanin=policy.gate_monolith_compute_fanin,
            gate_monolith_on_parse_error=policy.gate_monolith_on_parse_error,
            gate_monolith_areas_prefixes=policy.gate_monolith_areas_prefixes,
            gate_monolith_areas_names=policy.gate_monolith_areas_names,
            gate_monolith_areas_dynamic=policy.gate_monolith_areas_dynamic,
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
            gate_monolith_extensions=policy.gate_monolith_extensions,
            gate_monolith_compute_fanin=policy.gate_monolith_compute_fanin,
            gate_monolith_on_parse_error=policy.gate_monolith_on_parse_error,
            gate_monolith_areas_prefixes=policy.gate_monolith_areas_prefixes,
            gate_monolith_areas_names=policy.gate_monolith_areas_names,
            gate_monolith_areas_dynamic=policy.gate_monolith_areas_dynamic,
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

        commit_sha: str | None = None
        push_ok: bool | None = None

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

        workspace_deleted = False
        if policy.delete_workspace_on_success and policy.commit_and_push:
            delete_workspace(logger, ws)
            workspace_deleted = True
        elif policy.delete_workspace_on_success and not policy.commit_and_push:
            logger.line("workspace_delete=SKIPPED (disable-promotion)")

        if push_ok is True and workspace_deleted:
            run_post_success_audit(logger, repo_root, policy)

        exit_code = 0
    except RunnerError as e:
        logger.section("FAILURE")
        logger.line(str(e))
        logger.line(fingerprint(e))

        final_fail_stage = str(e.stage)
        final_fail_reason = str(e.message)

        stages: list[str] = []
        if primary_fail_stage is not None and primary_fail_stage == "PATCH":
            stages.append("PATCH_APPLY")
        for stg, _msg in secondary_failures:
            if stg == "PROMOTION":
                stages.append("PROMOTE")
            elif stg == "SCOPE":
                stages.append("SCOPE")
            elif stg:
                stages.append(stg)

        if e.stage == "GATES":
            msg = str(e.message)
            gates = _parse_gate_list(msg)
            for g in gates:
                stages.append(f"GATE_{g.upper()}")
            if not gates:
                stages.append("GATES")
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

        uniq: list[str] = []
        for s in stages:
            if s and s not in uniq:
                uniq.append(s)
        uniq.sort(key=lambda s: (_stage_rank(s), s))
        final_fail_stage = ", ".join(uniq) if uniq else (final_fail_stage or "INTERNAL")

        exit_code = 1

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
