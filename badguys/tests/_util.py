from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_cmd(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(argv), cwd=str(cwd), capture_output=True, text=True)


def append_log(log_path: Path, cp: subprocess.CompletedProcess[str]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        args = cp.args if isinstance(cp.args, list) else [str(cp.args)]
        f.write("$ " + " ".join(str(a) for a in args) + "\n")
        if cp.stdout:
            f.write(cp.stdout)
            if not cp.stdout.endswith("\n"):
                f.write("\n")
        if cp.stderr:
            f.write(cp.stderr)
            if not cp.stderr.endswith("\n"):
                f.write("\n")


def write_git_add_file_patch(patch_path: Path, rel_path: str, text: str) -> None:
    """Write a minimal 'git apply' patch that adds a new file with given text."""
    if not text.endswith("\n"):
        text = text + "\n"
    lines = text.splitlines(True)
    body = "".join(["+" + ln for ln in lines])
    content = (
        f"diff --git a/{rel_path} b/{rel_path}\n"
        f"new file mode 100644\n"
        f"index 0000000..1111111\n"
        f"--- /dev/null\n"
        f"+++ b/{rel_path}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        f"{body}"
    )
    write_text(patch_path, content)


def write_git_replace_line_patch(
    patch_path: Path,
    rel_path: str,
    context_line: str,
    old_line: str,
    new_line: str,
) -> None:
    """Replace a single line using a context line (for stable patching)."""
    if not context_line.endswith("\n"):
        context_line += "\n"
    if not old_line.endswith("\n"):
        old_line += "\n"
    if not new_line.endswith("\n"):
        new_line += "\n"
    content = (
        f"diff --git a/{rel_path} b/{rel_path}\n"
        f"index 1111111..2222222 100644\n"
        f"--- a/{rel_path}\n"
        f"+++ b/{rel_path}\n"
        f"@@ -1,2 +1,2 @@\n"
        f" {context_line}"
        f"-{old_line}"
        f"+{new_line}"
    )
    write_text(patch_path, content)


def _lock_path(repo_root: Path) -> Path:
    return repo_root / "patches" / "badguys.lock"


def _parse_lock_started(lock_path: Path) -> Optional[int]:
    try:
        txt = lock_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    for line in txt.splitlines():
        if line.startswith("started="):
            try:
                return int(line.split("=", 1)[1].strip())
            except ValueError:
                return None
    return None


def acquire_lock(
    repo_root: Path,
    *,
    path: Optional[Path] = None,
    ttl_seconds: int = 3600,
    on_conflict: str = "fail",
) -> None:
    lock_path = path if path is not None else _lock_path(repo_root)
    lock_path = lock_path if lock_path.is_absolute() else (repo_root / lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError as e:
        if on_conflict != "steal":
            raise SystemExit(f"FAIL: lock exists: {lock_path}") from e

        started = _parse_lock_started(lock_path)
        now = int(time.time())
        stale = started is not None and (now - started) > int(ttl_seconds)
        if not stale:
            raise SystemExit(f"FAIL: lock exists (not stale): {lock_path}") from e

        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass

        # retry once
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)

    try:
        content = f"pid={os.getpid()}\nstarted={int(time.time())}\n"
        os.write(fd, content.encode("utf-8"))
    finally:
        os.close(fd)


def release_lock(repo_root: Path, *, path: Optional[Path] = None) -> None:
    lock_path = path if path is not None else _lock_path(repo_root)
    lock_path = lock_path if lock_path.is_absolute() else (repo_root / lock_path)
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


def init_logs(repo_root: Path, run_id: str) -> Path:
    logs_dir = repo_root / "patches" / "badguys_logs"
    if logs_dir.exists():
        shutil.rmtree(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    central = repo_root / "patches" / f"badguys_{run_id}.log"
    central.parent.mkdir(parents=True, exist_ok=True)
    central.write_text(f"badguys run_id={run_id}\n", encoding="utf-8")
    return central


def print_result(test_name: str, ok: bool) -> None:
    status = "OK" if ok else "FAIL"
    print(f"badguys::{test_name} ... {status}")


def fail_commit_limit(central_log: Path, commit_limit: int, commit_tests: Sequence[object]) -> None:
    names = []
    for t in commit_tests:
        name = getattr(t, "name", None)
        if isinstance(name, str):
            names.append(name)
        else:
            names.append(str(t))

    msg = f"FAIL: commit_limit exceeded: selected={len(names)} limit={commit_limit}"
    with central_log.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")
        f.write("Commit tests selected:\n")
        for n in names:
            f.write(f" - {n}\n")
        f.write("Fix: increase --commit-limit OR exclude some commit tests OR include only one.\n")

    print(msg, file=sys.stderr)
    for n in names:
        print(f" - {n}", file=sys.stderr)
    print("Fix: increase --commit-limit OR use --exclude/--include.", file=sys.stderr)
    raise SystemExit(1)
