from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from am_patch.archive import archive_patch
from am_patch.artifacts import build_artifacts
from am_patch.errors import RunnerError
from am_patch.post_success_audit import run_post_success_audit
from am_patch.run_result import RunResult, _normalize_failure_summary
from am_patch.runtime import _parse_gate_list, _stage_rank
from am_patch.workspace import Workspace, delete_workspace, rollback_to_checkpoint


def _resolve_workspace_archive_path(
    *,
    result: RunResult,
    cli: Any,
    repo_root: Path,
    paths: Any,
    issue_id: str,
    logger: Any,
) -> Path | None:
    archived_path = result.used_patch_for_zip

    if result.exit_code == 0:
        if (
            archived_path is None
            and result.patch_script is not None
            and result.patch_script.exists()
        ):
            archived_path = archive_patch(logger, result.patch_script, paths.successful_dir)
        return archived_path

    patch_source: Path | None = None
    if result.patch_script is not None:
        patch_source = result.patch_script
    elif cli.patch_script:
        raw = Path(cli.patch_script)
        if raw.is_absolute():
            patch_source = raw
        else:
            repo_candidate = (repo_root / raw).resolve()
            patch_dir_candidate = (paths.patch_dir / raw).resolve()
            patch_source = repo_candidate if repo_candidate.exists() else patch_dir_candidate
    else:
        patch_source = (paths.patch_dir / f"issue_{issue_id}.py").resolve()

    candidates: list[Path] = []
    if patch_source is not None:
        candidates.append(patch_source)
        candidates.append((paths.patch_dir / patch_source.name).resolve())

    unique_candidates: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(candidate)

    for candidate in unique_candidates:
        if candidate.exists():
            return archive_patch(logger, candidate, paths.unsuccessful_dir)

    logger.section("ARCHIVE PATCH")
    logger.line(f"no patch script found to archive; tried: {unique_candidates}")
    return None


def _maybe_run_success_audit(
    *,
    logger: Any,
    repo_root: Path,
    policy: Any,
    result: RunResult,
) -> int:
    if result.exit_code != 0 or result.push_ok_for_posthook is not True:
        return result.exit_code

    try:
        run_post_success_audit(logger, repo_root, policy)
        return result.exit_code
    except Exception as audit_error:
        result.exit_code = 1
        logger.section("AUDIT")
        logger.line(f"post_success_audit_failed={audit_error!r}")
        if isinstance(audit_error, RunnerError):
            stage, reason = _normalize_failure_summary(
                error=audit_error,
                primary_fail_stage=result.primary_fail_stage,
                secondary_failures=result.secondary_failures,
                parse_gate_list=_parse_gate_list,
                stage_rank=_stage_rank,
            )
            result.final_fail_stage = stage
            result.final_fail_reason = reason
        else:
            result.final_fail_stage = "AUDIT"
            result.final_fail_reason = "audit failed"
        return result.exit_code


def run_post_run_pipeline(*, ctx: Any, result: RunResult) -> int:
    cli = ctx.cli
    policy = ctx.policy
    repo_root = ctx.repo_root
    paths = ctx.paths
    log_path = ctx.log_path
    logger = ctx.logger

    try:
        if cli.mode in ("workspace", "finalize", "finalize_workspace") and not policy.test_mode:
            issue_id = str(cli.issue_id or "unknown")
            archived_path: Path | None = None
            if cli.mode == "workspace":
                archived_path = _resolve_workspace_archive_path(
                    result=result,
                    cli=cli,
                    repo_root=repo_root,
                    paths=paths,
                    issue_id=issue_id,
                    logger=logger,
                )

            run_audit_after_workspace_delete = (
                result.exit_code == 0
                and result.push_ok_for_posthook is True
                and cli.mode in ("workspace", "finalize_workspace")
                and result.delete_workspace_after_archive
                and result.ws_for_posthook is not None
            )
            workspace_deleted_before_audit = False
            if run_audit_after_workspace_delete:
                workspace_for_delete = cast(Workspace, result.ws_for_posthook)
                delete_workspace(logger, workspace_for_delete)
                workspace_deleted_before_audit = True

            _maybe_run_success_audit(
                logger=logger,
                repo_root=repo_root,
                policy=policy,
                result=result,
            )

            if workspace_deleted_before_audit:
                ws_repo_for_fail_zip = repo_root
            elif result.ws_for_posthook is not None and result.ws_for_posthook.repo.exists():
                ws_repo_for_fail_zip = result.ws_for_posthook.repo
            else:
                ws_repo_for_fail_zip = paths.workspaces_dir / f"issue_{issue_id}" / "repo"

            build_artifacts(
                logger=logger,
                cli=cli,
                policy=policy,
                paths=paths,
                repo_root=repo_root,
                log_path=log_path,
                exit_code=result.exit_code,
                unified_mode=result.unified_mode,
                patch_applied_successfully=result.patch_applied_successfully,
                archived_patch=archived_path,
                failed_patch_blobs_for_zip=result.failed_patch_blobs_for_zip,
                files_for_fail_zip=result.files_for_fail_zip,
                ws_repo_for_fail_zip=ws_repo_for_fail_zip,
                ws_attempt=(
                    result.ws_for_posthook.attempt if result.ws_for_posthook is not None else None
                ),
                issue_diff_base_sha=result.issue_diff_base_sha,
                issue_diff_paths=result.issue_diff_paths,
            )
            if (
                result.exit_code != 0
                and result.rollback_ws_for_posthook is not None
                and result.rollback_ckpt_for_posthook is not None
            ):
                mode = getattr(policy, "rollback_workspace_on_fail", "none-applied")
                do_rollback = False
                if mode == "always":
                    do_rollback = True
                elif mode == "none-applied":
                    do_rollback = result.applied_ok_count == 0

                if do_rollback:
                    logger.line(
                        f"ROLLBACK: executed (mode={mode} applied_ok={result.applied_ok_count})"
                    )
                    rollback_to_checkpoint(
                        logger,
                        result.rollback_ws_for_posthook.repo,
                        result.rollback_ckpt_for_posthook,
                    )
                else:
                    logger.line(
                        f"ROLLBACK: skipped (mode={mode} applied_ok={result.applied_ok_count})"
                    )

            if (
                result.exit_code == 0
                and result.delete_workspace_after_archive
                and result.ws_for_posthook is not None
                and not workspace_deleted_before_audit
            ):
                delete_workspace(logger, cast(Workspace, result.ws_for_posthook))
    except Exception as posthook_error:
        try:
            logger.section("POSTHOOK-ERROR")
            logger.line(repr(posthook_error))
        except Exception:
            pass

    if cli.mode == "workspace" and policy.test_mode:
        try:
            logger.section("TEST MODE CLEANUP")
            if result.ws_for_posthook is None:
                logger.line("workspace_present=0")
            else:
                logger.line("workspace_present=1")
                logger.line(f"workspace_root={result.ws_for_posthook.root}")
                logger.line("workspace_delete=1")
                delete_workspace(logger, cast(Workspace, result.ws_for_posthook))
        except Exception as cleanup_error:
            try:
                logger.section("TEST_MODE_CLEANUP_ERROR")
                logger.line(repr(cleanup_error))
            except Exception:
                pass

    return result.exit_code
