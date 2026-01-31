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


class Logger:
    def __init__(self, log_path: Path, symlink_path: Path, tee_to_screen: bool = True) -> None:
        self.log_path = log_path
        self.symlink_path = symlink_path
        self.tee_to_screen = tee_to_screen

        log_path.parent.mkdir(parents=True, exist_ok=True)
        symlink_path.parent.mkdir(parents=True, exist_ok=True)

        self._fp = open(log_path, "w", encoding="utf-8", errors="replace")

        try:
            if symlink_path.exists() or symlink_path.is_symlink():
                symlink_path.unlink()
            target_rel = Path("logs") / log_path.name
            symlink_path.symlink_to(target_rel)
        except Exception:
            pass

    def close(self) -> None:
        try:
            self._fp.flush()
        finally:
            self._fp.close()

    def _tee(self, s: str) -> None:
        if self.tee_to_screen:
            sys.stdout.write(s)
            sys.stdout.flush()

    def write(self, s: str) -> None:
        self._fp.write(s)
        self._fp.flush()
        self._tee(s)

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
        self.section("RUN")
        self.line(f"cmd: {argv}")
        if cwd is not None:
            self.line(f"cwd: {str(cwd)}")
        self.line("---- stdout+stderr (captured) ----")

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

        self.line(f"returncode: {p.returncode}")
        return RunResult(argv=argv, returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)


def new_log_file(logs_dir: Path, issue_id: str | None) -> Path:
    ts = time.strftime("%Y%m%d_%H%M%S")
    if issue_id:
        name = f"am_patch_issue_{issue_id}_{ts}.log"
    else:
        name = f"am_patch_finalize_{ts}.log"
    return logs_dir / name
