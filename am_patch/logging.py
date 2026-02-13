from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .deps import FileOps


@dataclass
class RunLogger:
    path: Path

    def write_line(self, line: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line.rstrip("\n") + "\n")

    def phase_start(self, phase: str) -> None:
        self.write_line(f"PHASE_START {phase}")

    def phase_end(self, phase: str, ok: bool, detail: str = "") -> None:
        d = detail.replace("\n", " ").strip()
        if d:
            self.write_line(f"PHASE_END {phase} ok={ok} detail={d}")
        else:
            self.write_line(f"PHASE_END {phase} ok={ok}")


def default_log_path(repo_root: Path, issue_id: str | None) -> Path:
    iid = issue_id or "unknown"
    return repo_root / "patches" / "logs" / f"am_patch_root_issue_{iid}.log"
