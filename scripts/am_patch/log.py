from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .console import colorize_console_message, stdout_color_enabled


@dataclass
class RunResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


Severity = str  # DEBUG|INFO|WARNING|ERROR
Channel = str  # CORE|DETAIL


_LEVELS = ("quiet", "normal", "warning", "verbose", "debug")
_SEVERITIES = ("DEBUG", "INFO", "WARNING", "ERROR")
_CHANNELS = ("CORE", "DETAIL")


def _allowed(level: str, severity: Severity, channel: Channel, *, summary: bool) -> bool:
    """Return whether a message is allowed at a given level.

    Semantics are defined by the issue 999 handoff (shared for screen and log).

    Levels are inherited (each higher includes everything from the lower):

    - quiet:
        * START + RESULT only (summary=True bypass)
    - normal:
        * quiet + legacy concise flow lines (CORE)
    - warning:
        * normal + warnings (DETAIL+WARNING)
    - verbose:
        * warning + diagnostic sections (DETAIL+INFO)
    - debug:
        * verbose + DEBUG metadata (DETAIL+DEBUG)

    Full error detail (stdout/stderr) bypasses filtering and is handled
    via Logger.emit(..., error_detail=True).
    """

    lvl = (level or "").strip().lower()
    sev = (severity or "").strip().upper()
    ch = (channel or "").strip().upper()

    if lvl not in _LEVELS:
        lvl = "verbose"
    if sev not in _SEVERITIES:
        sev = "INFO"
    if ch not in _CHANNELS:
        ch = "DETAIL"

    if summary:
        return True

    if lvl == "quiet":
        return False

    if lvl == "normal":
        return ch == "CORE" and sev in ("INFO", "WARNING", "ERROR")

    if lvl == "warning":
        if ch == "CORE":
            return sev in ("INFO", "WARNING", "ERROR")
        return sev == "WARNING"

    if lvl == "verbose":
        if ch == "CORE":
            return sev in ("INFO", "WARNING", "ERROR")
        return sev in ("INFO", "WARNING")

    # debug
    return True


class Logger:
    def __init__(
        self,
        *,
        log_path: Path,
        symlink_path: Path,
        screen_level: str,
        log_level: str,
        console_color: str = "auto",
        symlink_enabled: bool = True,
        symlink_target_rel: Path | None = None,
        json_enabled: bool = False,
        json_path: Path | None = None,
        stage_provider: Callable[[], str] | None = None,
    ) -> None:
        self.log_path = log_path
        self.symlink_path = symlink_path
        self.screen_level = str(screen_level or "").strip().lower() or "verbose"
        self.log_level = str(log_level or "").strip().lower() or "verbose"
        self.symlink_enabled = symlink_enabled
        self.symlink_target_rel = symlink_target_rel

        self.json_enabled = bool(json_enabled)
        self.json_path = json_path
        self._stage_provider = stage_provider
        self._json_fp = None
        self._json_seq = 0
        self._mono_start = time.monotonic()

        self.console_color = str(console_color or "").strip().lower() or "auto"
        self._console_color_enabled = stdout_color_enabled(self.console_color)

        log_path.parent.mkdir(parents=True, exist_ok=True)
        symlink_path.parent.mkdir(parents=True, exist_ok=True)

        self._fp = open(log_path, "w", encoding="utf-8", errors="replace")  # noqa: SIM115

        if self.json_enabled and self.json_path is not None:
            self.json_path.parent.mkdir(parents=True, exist_ok=True)
            self._json_fp = open(self.json_path, "w", encoding="utf-8", errors="replace")  # noqa: SIM115

        if self.symlink_enabled:
            try:
                if symlink_path.exists() or symlink_path.is_symlink():
                    symlink_path.unlink()
                target_rel = self.symlink_target_rel
                if target_rel is None:
                    target_rel = Path("logs") / log_path.name
                symlink_path.symlink_to(target_rel)
            except Exception:
                pass

    def close(self) -> None:
        try:
            self._fp.flush()
        finally:
            self._fp.close()

    def _write_file(self, s: str) -> None:
        self._fp.write(s)
        self._fp.flush()

    def _write_screen(self, s: str) -> None:
        if self._console_color_enabled:
            with contextlib.suppress(Exception):
                s = colorize_console_message(s, enabled=True)
        sys.stdout.write(s)
        sys.stdout.flush()

    def _now_mono_ms(self) -> int:
        return int((time.monotonic() - self._mono_start) * 1000)

    def _get_stage(self) -> str:
        if self._stage_provider is None:
            return "PREFLIGHT"
        with contextlib.suppress(Exception):
            s = str(self._stage_provider() or "").strip()
            if s:
                return s
        return "PREFLIGHT"

    def _write_json(self, obj: dict[str, Any]) -> None:
        if self._json_fp is None:
            return
        line = json.dumps(obj, ensure_ascii=True, separators=(",", ":"))
        self._json_fp.write(line + "\n")
        self._json_fp.flush()

    def emit(
        self,
        *,
        severity: Severity,
        channel: Channel,
        message: str,
        summary: bool = False,
        error_detail: bool = False,
        kind: str | None = None,
        to_screen: bool = True,
        to_log: bool = True,
    ) -> None:
        # One-line discipline: caller controls newlines.
        if self.json_enabled and self._json_fp is not None:
            self._json_seq += 1
            msg = message
            if msg.endswith("\n"):
                msg = msg[:-1]
            evt = {
                "type": "log",
                "seq": self._json_seq,
                "ts_mono_ms": self._now_mono_ms(),
                "stage": self._get_stage(),
                "kind": kind or "TEXT",
                "sev": str(severity or "").strip().upper() or "INFO",
                "ch": str(channel or "").strip().upper() or "DETAIL",
                "summary": bool(summary),
                "bypass": bool(error_detail),
                "msg": msg,
            }
            with contextlib.suppress(Exception):
                self._write_json(evt)

        if to_log and (
            error_detail or _allowed(self.log_level, severity, channel, summary=summary)
        ):
            self._write_file(message)
        if to_screen and (
            error_detail or _allowed(self.screen_level, severity, channel, summary=summary)
        ):
            self._write_screen(message)

    def emit_json_hello(
        self, *, issue_id: str | None, mode: str, verbosity: str, log_level: str
    ) -> None:
        if not self.json_enabled or self._json_fp is None:
            return
        self._json_seq += 1
        evt = {
            "type": "hello",
            "protocol": "am_patch_ndjson/1",
            "seq": self._json_seq,
            "ts_mono_ms": self._now_mono_ms(),
            "runner_mode": str(mode or ""),
            "issue_id": issue_id,
            "screen_level": str(verbosity or ""),
            "log_level": str(log_level or ""),
        }
        with contextlib.suppress(Exception):
            self._write_json(evt)

    def emit_json_result(
        self, *, ok: bool, return_code: int, log_path: Path, json_path: Path | None
    ) -> None:
        if not self.json_enabled or self._json_fp is None:
            return
        self._json_seq += 1
        evt = {
            "type": "result",
            "seq": self._json_seq,
            "ts_mono_ms": self._now_mono_ms(),
            "ok": bool(ok),
            "return_code": int(return_code),
            "log_path": str(log_path),
            "json_path": str(json_path) if json_path is not None else None,
        }
        with contextlib.suppress(Exception):
            self._write_json(evt)

    def emit_json_failed_step_detail(self, *, stdout: str, stderr: str) -> None:
        if not self.json_enabled or self._json_fp is None:
            return
        self._json_seq += 1
        evt = {
            "type": "log",
            "seq": self._json_seq,
            "ts_mono_ms": self._now_mono_ms(),
            "stage": self._get_stage(),
            "kind": "TEXT",
            "sev": "ERROR",
            "ch": "CORE",
            "summary": False,
            "bypass": True,
            "msg": "FAILED STEP OUTPUT",
            "stdout": stdout,
            "stderr": stderr,
        }
        with contextlib.suppress(Exception):
            self._write_json(evt)

    # Convenience methods
    def debug_detail(self, s: str) -> None:
        self.emit(severity="DEBUG", channel="DETAIL", message=s + "\n")

    def info_core(self, s: str) -> None:
        self.emit(severity="INFO", channel="CORE", message=s + "\n")

    def warning_core(self, s: str) -> None:
        self.emit(severity="WARNING", channel="CORE", message=s + "\n")

    def error_core(self, s: str) -> None:
        self.emit(severity="ERROR", channel="CORE", message=s + "\n")

    def summary(self, s: str) -> None:
        self.emit(severity="INFO", channel="CORE", message=s + "\n", summary=True)

    # Backward-compatible API (DETAIL+INFO)
    def write(self, s: str) -> None:
        self.emit(severity="INFO", channel="DETAIL", message=s)

    def line(self, s: str = "") -> None:
        self.write(s + "\n")

    def section(self, title: str) -> None:
        # Diagnostic section banners must not appear in normal/warning.
        self.emit(severity="INFO", channel="DETAIL", message="\n")
        self.emit(severity="INFO", channel="DETAIL", message=("=" * 80) + "\n")
        self.emit(severity="INFO", channel="DETAIL", message=title + "\n")
        self.emit(severity="INFO", channel="DETAIL", message=("=" * 80) + "\n")

    def emit_error_detail(self, s: str) -> None:
        # Full error detail must bypass filtering (visible even in quiet).
        self.emit(severity="ERROR", channel="CORE", message=s, error_detail=True)

    def run_logged(
        self,
        argv: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> RunResult:
        # RUN metadata must not appear in normal/warning/verbose; keep it in DETAIL+DEBUG.
        self.emit(severity="DEBUG", channel="DETAIL", message="RUN\n")
        self.emit(severity="DEBUG", channel="DETAIL", message=f"cmd={argv}\n")
        if cwd is not None:
            self.emit(severity="DEBUG", channel="DETAIL", message=f"cwd={str(cwd)}\n")

        p = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            env=env,
            text=True,
            capture_output=True,
        )

        if p.returncode != 0:
            self.emit_json_failed_step_detail(stdout=p.stdout or "", stderr=p.stderr or "")
            # Full error detail must always be visible (stdout+stderr), even in quiet.
            self.emit_error_detail("\n" + ("=" * 80) + "\nFAILED STEP OUTPUT\n" + ("=" * 80) + "\n")
            if p.stdout:
                self.emit_error_detail("[stdout]\n")
                self.emit_error_detail(p.stdout)
                if not p.stdout.endswith("\n"):
                    self.emit_error_detail("\n")
            if p.stderr:
                self.emit_error_detail("[stderr]\n")
                self.emit_error_detail(p.stderr)
                if not p.stderr.endswith("\n"):
                    self.emit_error_detail("\n")

        return RunResult(argv=argv, returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)


def new_log_file(
    logs_dir: Path,
    issue_id: str | None,
    *,
    ts_format: str = "%Y%m%d_%H%M%S",
    issue_template: str = "am_patch_issue_{issue}_{ts}.log",
    finalize_template: str = "am_patch_finalize_{ts}.log",
) -> Path:
    ts = time.strftime(ts_format)
    if issue_id:
        name = issue_template.format(issue=issue_id, ts=ts)
    else:
        name = finalize_template.format(ts=ts)
    return logs_dir / name
