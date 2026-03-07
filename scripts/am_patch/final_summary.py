from __future__ import annotations

from pathlib import Path

from am_patch.errors import CANCEL_EXIT_CODE
from am_patch.log import Logger


def _emit_summary_line(
    logger: Logger,
    *,
    message: str,
    kind: str,
    to_screen: bool,
    to_log: bool,
) -> None:
    logger.emit(
        severity="INFO",
        channel="CORE",
        message=message,
        kind=kind,
        summary=True,
        to_screen=to_screen,
        to_log=to_log,
    )


def emit_final_summary(
    *,
    logger: Logger,
    log_path: Path,
    exit_code: int,
    commit_and_push: bool,
    final_commit_sha: str | None,
    final_pushed_files: list[str] | None,
    push_ok_for_posthook: bool | None,
    final_fail_stage: str | None,
    final_fail_reason: str | None,
    screen_quiet: bool,
    log_quiet: bool,
) -> None:
    if exit_code == 0:
        _emit_success_summary(
            logger=logger,
            log_path=log_path,
            commit_and_push=commit_and_push,
            final_commit_sha=final_commit_sha,
            final_pushed_files=final_pushed_files,
            push_ok_for_posthook=push_ok_for_posthook,
            screen_quiet=screen_quiet,
            log_quiet=log_quiet,
        )
        return

    if exit_code == CANCEL_EXIT_CODE:
        _emit_canceled_summary(
            logger=logger,
            log_path=log_path,
            stage=final_fail_stage,
            screen_quiet=screen_quiet,
            log_quiet=log_quiet,
        )
        return

    _emit_fail_summary(
        logger=logger,
        log_path=log_path,
        stage=final_fail_stage,
        reason=final_fail_reason,
        screen_quiet=screen_quiet,
        log_quiet=log_quiet,
    )


def _emit_success_summary(
    *,
    logger: Logger,
    log_path: Path,
    commit_and_push: bool,
    final_commit_sha: str | None,
    final_pushed_files: list[str] | None,
    push_ok_for_posthook: bool | None,
    screen_quiet: bool,
    log_quiet: bool,
) -> None:
    _emit_summary_line(
        logger,
        message="RESULT: SUCCESS\n",
        kind="RESULT",
        to_screen=True,
        to_log=True,
    )
    if push_ok_for_posthook is True and final_pushed_files is not None:
        _emit_summary_line(
            logger,
            message="FILES:\n\n",
            kind="FILES",
            to_screen=not screen_quiet,
            to_log=not log_quiet,
        )
        for line in final_pushed_files:
            _emit_summary_line(
                logger,
                message=f"{line}\n",
                kind="TEXT",
                to_screen=not screen_quiet,
                to_log=not log_quiet,
            )
    _emit_summary_line(
        logger,
        message=f"COMMIT: {final_commit_sha or '(none)'}\n",
        kind="COMMIT",
        to_screen=not screen_quiet,
        to_log=not log_quiet,
    )
    if commit_and_push:
        if push_ok_for_posthook is True:
            push_txt = "OK"
        elif push_ok_for_posthook is False:
            push_txt = "FAIL"
        else:
            push_txt = "UNKNOWN"
        _emit_summary_line(
            logger,
            message=f"PUSH: {push_txt}\n",
            kind="PUSH",
            to_screen=not screen_quiet,
            to_log=not log_quiet,
        )
    _emit_summary_line(
        logger,
        message=f"LOG: {log_path}\n",
        kind="TEXT",
        to_screen=not screen_quiet,
        to_log=True,
    )


def _emit_canceled_summary(
    *,
    logger: Logger,
    log_path: Path,
    stage: str | None,
    screen_quiet: bool,
    log_quiet: bool,
) -> None:
    _emit_summary_line(
        logger,
        message="RESULT: CANCELED\n",
        kind="RESULT",
        to_screen=True,
        to_log=True,
    )
    _emit_summary_line(
        logger,
        message=f"STAGE: {stage or 'INTERNAL'}\n",
        kind="STAGE",
        to_screen=not screen_quiet,
        to_log=True,
    )
    _emit_summary_line(
        logger,
        message="REASON: cancel requested\n",
        kind="REASON",
        to_screen=not screen_quiet,
        to_log=True,
    )
    _emit_summary_line(
        logger,
        message=f"LOG: {log_path}\n",
        kind="TEXT",
        to_screen=not screen_quiet,
        to_log=True,
    )


def _emit_fail_summary(
    *,
    logger: Logger,
    log_path: Path,
    stage: str | None,
    reason: str | None,
    screen_quiet: bool,
    log_quiet: bool,
) -> None:
    _emit_summary_line(
        logger,
        message="RESULT: FAIL\n",
        kind="RESULT",
        to_screen=True,
        to_log=True,
    )
    _emit_summary_line(
        logger,
        message=f"STAGE: {stage or 'INTERNAL'}\n",
        kind="STAGE",
        to_screen=not screen_quiet,
        to_log=not log_quiet,
    )
    _emit_summary_line(
        logger,
        message=f"REASON: {reason or 'unexpected error'}\n",
        kind="REASON",
        to_screen=not screen_quiet,
        to_log=not log_quiet,
    )
    _emit_summary_line(
        logger,
        message=f"LOG: {log_path}\n",
        kind="TEXT",
        to_screen=not screen_quiet,
        to_log=not log_quiet,
    )
