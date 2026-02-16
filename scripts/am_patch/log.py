from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


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

    Semantics are defined by the issue handoff (shared for screen and log):
    - quiet: CORE(ERROR) + final summary
    - normal: CORE(INFO/ERROR) + final summary
    - warning: CORE(INFO/WARNING/ERROR) + final summary
    - verbose: CORE(*) + final summary, DETAIL(INFO/WARNING/ERROR)
    - debug: all CORE + final summary, all DETAIL including DEBUG
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
        return ch == "CORE" and sev == "ERROR"
    if lvl == "normal":
        return ch == "CORE" and sev in ("INFO", "ERROR")
    if lvl == "warning":
        return ch == "CORE" and sev in ("INFO", "WARNING", "ERROR")
    if lvl == "verbose":
        if ch == "CORE":
            return sev in ("INFO", "WARNING", "ERROR")
        # DETAIL
        return sev in ("INFO", "WARNING", "ERROR")
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
        symlink_enabled: bool = True,
        symlink_target_rel: Path | None = None,
    ) -> None:
        self.log_path = log_path
        self.symlink_path = symlink_path
        self.screen_level = str(screen_level or "").strip().lower() or "verbose"
        self.log_level = str(log_level or "").strip().lower() or "verbose"
        self.symlink_enabled = symlink_enabled
        self.symlink_target_rel = symlink_target_rel

        log_path.parent.mkdir(parents=True, exist_ok=True)
        symlink_path.parent.mkdir(parents=True, exist_ok=True)

        self._fp = open(log_path, "w", encoding="utf-8", errors="replace")  # noqa: SIM115

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
        sys.stdout.write(s)
        sys.stdout.flush()

    def emit(
        self,
        *,
        severity: Severity,
        channel: Channel,
        message: str,
        summary: bool = False,
        to_screen: bool = True,
        to_log: bool = True,
    ) -> None:
        # One-line discipline: caller controls newlines.
        if to_log and _allowed(self.log_level, severity, channel, summary=summary):
            self._write_file(message)
        if to_screen and _allowed(self.screen_level, severity, channel, summary=summary):
            self._write_screen(message)

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
        self.line("")
        self.line("=" * 80)
        self.line(title)
        self.line("=" * 80)

    def run_logged(
        self,
        argv: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> RunResult:
        # CORE metadata (must be present at log_level=normal)
        self.info_core("RUN")
        self.info_core(f"cmd={argv}")
        if cwd is not None:
            self.info_core(f"cwd={str(cwd)}")

        # DETAIL capture output
        self.section("RUN (captured stdout+stderr)")
        p = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            env=env,
            text=True,
            capture_output=True,
        )
        if p.stdout:
            self.line(p.stdout.rstrip("\n"))
        if p.stderr:
            self.line(p.stderr.rstrip("\n"))

        self.info_core(f"returncode={p.returncode}")
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
