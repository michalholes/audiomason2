from __future__ import annotations

import sys
from pathlib import Path

import pytest


def _import_am_patch():
    scripts_dir = Path(__file__).parent.parent / "scripts"
    sys.path.insert(0, str(scripts_dir))
    from am_patch.cli import parse_args
    from am_patch.log import Logger

    return Logger, parse_args


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


def test_logger_filters_screen_warning_level(capsys: pytest.CaptureFixture[str], tmp_path: Path):
    logger = _mk_logger(tmp_path, screen_level="warning", log_level="verbose")
    try:
        logger.info_core("CORE_INFO")
        logger.warning_core("CORE_WARN")
        logger.write("DETAIL_INFO\n")
    finally:
        logger.close()

    out = capsys.readouterr().out
    assert "CORE_INFO" in out
    assert "CORE_WARN" in out
    assert "DETAIL_INFO" not in out


def test_logger_filters_file_quiet_keeps_summary(tmp_path: Path):
    logger = _mk_logger(tmp_path, screen_level="quiet", log_level="quiet")
    try:
        logger.info_core("CORE_INFO")
        logger.warning_core("CORE_WARN")
        logger.error_core("CORE_ERR")
        logger.emit(
            severity="INFO",
            channel="CORE",
            message="SUMMARY_LINE\n",
            summary=True,
            to_screen=False,
        )
    finally:
        logger.close()

    data = (tmp_path / "am_patch.log").read_text(encoding="utf-8")
    assert "CORE_ERR" in data
    assert "SUMMARY_LINE" in data
    assert "CORE_INFO" not in data
    assert "CORE_WARN" not in data


def test_cli_accepts_warning_and_log_level():
    _, parse_args = _import_am_patch()
    ns = parse_args(["--verbosity", "warning", "--log-level", "warning", "1", "msg"])
    assert ns.verbosity == "warning"
    assert ns.log_level == "warning"
