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


def test_normal_shows_core_hides_detail_and_matches_log(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
):
    logger = _mk_logger(tmp_path, screen_level="normal", log_level="normal")
    try:
        logger.emit(severity="INFO", channel="CORE", message="DO: STAGE\n")
        logger.emit(severity="INFO", channel="DETAIL", message="DIAG\n")
    finally:
        logger.close()

    out = capsys.readouterr().out
    data = (tmp_path / "am_patch.log").read_text(encoding="utf-8")

    assert "DO: STAGE" in out
    assert "DIAG" not in out

    assert out == data


def test_error_detail_is_visible_even_in_quiet(capsys: pytest.CaptureFixture[str], tmp_path: Path):
    logger = _mk_logger(tmp_path, screen_level="quiet", log_level="quiet")
    try:
        logger.emit(severity="INFO", channel="CORE", message="CORE\n")
        logger.emit(severity="INFO", channel="DETAIL", message="DETAIL\n")
        logger.emit(
            severity="ERROR",
            channel="CORE",
            message="[stdout]\nhello\n",
            error_detail=True,
        )
    finally:
        logger.close()

    out = capsys.readouterr().out
    data = (tmp_path / "am_patch.log").read_text(encoding="utf-8")

    assert "CORE" not in out
    assert "DETAIL" not in out
    assert "hello" in out

    assert "CORE" not in data
    assert "DETAIL" not in data
    assert "hello" in data


def test_run_metadata_only_in_debug(capsys: pytest.CaptureFixture[str], tmp_path: Path):
    # verbose: debug metadata must be hidden
    logger_v = _mk_logger(tmp_path / "v", screen_level="verbose", log_level="verbose")
    try:
        _ = logger_v.run_logged([sys.executable, "-c", "print('ok')"], cwd=None)
    finally:
        logger_v.close()

    out_v = capsys.readouterr().out
    assert "cmd=" not in out_v

    # debug: debug metadata must be visible
    logger_d = _mk_logger(tmp_path / "d", screen_level="debug", log_level="debug")
    try:
        _ = logger_d.run_logged([sys.executable, "-c", "print('ok')"], cwd=None)
    finally:
        logger_d.close()

    out_d = capsys.readouterr().out
    assert "cmd=" in out_d


def test_cli_accepts_warning_and_log_level():
    _, parse_args = _import_am_patch()
    ns = parse_args(["--verbosity", "warning", "--log-level", "warning", "1", "msg"])
    assert ns.verbosity == "warning"
    assert ns.log_level == "warning"
