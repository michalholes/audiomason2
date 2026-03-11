from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from am_patch.errors import CANCEL_EXIT_CODE
from am_patch.log import Logger


def _emit_logger_message(
    logger: Logger,
    *,
    severity: str,
    channel: str,
    message: str,
    kind: str,
    summary: bool,
    error_detail: bool,
    to_screen: bool,
    to_log: bool,
) -> None:
    with suppress(Exception):
        logger.emit(
            severity=severity,
            channel=channel,
            message=message,
            kind=kind,
            summary=summary,
            error_detail=error_detail,
            to_screen=False,
            to_log=False,
        )
    if to_log:
        with suppress(Exception):
            logger._write_file(message)
    if to_screen:
        with suppress(Exception):
            logger._write_screen(message)


def _emit_summary_line(
    logger: Logger,
    *,
    message: str,
    kind: str,
    to_screen: bool,
    to_log: bool,
) -> None:
    _emit_logger_message(
        logger,
        severity="INFO",
        channel="CORE",
        message=message,
        kind=kind,
        summary=True,
        error_detail=False,
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
    final_fail_detail: str | None,
    final_fail_fingerprint: str | None,
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
        detail=final_fail_detail,
        fingerprint=final_fail_fingerprint,
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
    detail: str | None,
    fingerprint: str | None,
    screen_quiet: bool,
    log_quiet: bool,
) -> None:
    if detail:
        _emit_logger_message(
            logger,
            severity="ERROR",
            channel="CORE",
            message=detail,
            kind="TEXT",
            summary=False,
            error_detail=True,
            to_screen=True,
            to_log=True,
        )
    if fingerprint:
        _emit_logger_message(
            logger,
            severity="ERROR",
            channel="CORE",
            message=fingerprint,
            kind="TEXT",
            summary=False,
            error_detail=True,
            to_screen=False,
            to_log=True,
        )
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
