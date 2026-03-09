from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _import_am_patch():
    scripts_dir = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    from am_patch.final_summary import emit_final_summary
    from am_patch.log import Logger

    return Logger, emit_final_summary


def _mk_logger(tmp_path: Path, *, screen_level: str, log_level: str):
    logger_cls, _ = _import_am_patch()
    log_path = tmp_path / "am_patch.log"
    symlink_path = tmp_path / "am_patch.symlink"
    return logger_cls(
        log_path=log_path,
        symlink_path=symlink_path,
        screen_level=screen_level,
        log_level=log_level,
        symlink_enabled=False,
    )


def test_fail_summary_emits_detail_and_fingerprint(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
):
    _, emit_final_summary = _import_am_patch()
    logger = _mk_logger(tmp_path, screen_level="normal", log_level="normal")
    log_path = tmp_path / "am_patch.log"
    try:
        emit_final_summary(
            logger=logger,
            log_path=log_path,
            exit_code=1,
            commit_and_push=False,
            final_commit_sha=None,
            final_pushed_files=None,
            push_ok_for_posthook=None,
            final_fail_stage="PREFLIGHT",
            final_fail_reason="invalid inputs",
            final_fail_detail=("ERROR DETAIL: PREFLIGHT:PATCH_ASCII: bad patch\n"),
            final_fail_fingerprint=(
                "AM_PATCH_FAILURE_FINGERPRINT:\n- stage: PREFLIGHT\n- category: PATCH_ASCII\n"
            ),
            screen_quiet=False,
            log_quiet=False,
        )
    finally:
        logger.close()

    out = capsys.readouterr().out
    data = log_path.read_text(encoding="utf-8")

    assert "ERROR DETAIL: PREFLIGHT:PATCH_ASCII: bad patch" in out
    assert "RESULT: FAIL" in out
    assert "STAGE: PREFLIGHT" in out
    assert "REASON: invalid inputs" in out
    assert "AM_PATCH_FAILURE_FINGERPRINT" not in out
    assert "AM_PATCH_FAILURE_FINGERPRINT" in data


def test_fail_summary_keeps_quiet_screen_minimal_but_shows_error_detail(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
):
    _, emit_final_summary = _import_am_patch()
    logger = _mk_logger(tmp_path, screen_level="quiet", log_level="quiet")
    log_path = tmp_path / "am_patch.log"
    try:
        emit_final_summary(
            logger=logger,
            log_path=log_path,
            exit_code=1,
            commit_and_push=False,
            final_commit_sha=None,
            final_pushed_files=None,
            push_ok_for_posthook=None,
            final_fail_stage="PREFLIGHT",
            final_fail_reason="invalid inputs",
            final_fail_detail=("ERROR DETAIL: PREFLIGHT:PATCH_ASCII: bad patch\n"),
            final_fail_fingerprint=(
                "AM_PATCH_FAILURE_FINGERPRINT:\n- stage: PREFLIGHT\n- category: PATCH_ASCII\n"
            ),
            screen_quiet=True,
            log_quiet=True,
        )
    finally:
        logger.close()

    out = capsys.readouterr().out
    data = log_path.read_text(encoding="utf-8")

    assert "ERROR DETAIL: PREFLIGHT:PATCH_ASCII: bad patch" in out
    assert "RESULT: FAIL" in out
    assert "STAGE: PREFLIGHT" not in out
    assert "REASON: invalid inputs" not in out
    assert "AM_PATCH_FAILURE_FINGERPRINT" not in out
    assert "ERROR DETAIL: PREFLIGHT:PATCH_ASCII: bad patch" in data
    assert "AM_PATCH_FAILURE_FINGERPRINT" in data
