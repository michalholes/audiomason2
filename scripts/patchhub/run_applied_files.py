from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

_SUMMARY_STOP_RE = re.compile(r"^[A-Z][A-Z_ ]+:\s*")


def _find_latest_artifact_rel(patches_root: Path, dir_name: str, contains: str) -> str | None:
    base = patches_root / dir_name
    if not base.exists() or not base.is_dir():
        return None
    best_name = None
    best_mtime = -1.0
    for item in base.iterdir():
        if not item.is_file():
            continue
        if contains not in item.name:
            continue
        try:
            st = item.stat()
        except Exception:
            continue
        if st.st_mtime > best_mtime:
            best_mtime = st.st_mtime
            best_name = item.name
    if not best_name:
        return None
    return str(Path(dir_name) / best_name)


def _parse_diff_manifest(data: bytes) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    text = data.decode("utf-8", errors="replace")
    for raw in text.splitlines():
        if not raw.startswith("FILE "):
            continue
        path = raw[5:].strip()
        if not path or path in seen:
            continue
        seen.add(path)
        files.append(path)
    return files


def _parse_final_summary_files(text: str) -> list[str]:
    lines = text.splitlines()
    start_idx = -1
    for idx, raw in enumerate(lines):
        if raw.strip() == "FILES:":
            start_idx = idx + 1
    if start_idx < 0:
        return []

    files: list[str] = []
    seen: set[str] = set()
    started = False
    for raw in lines[start_idx:]:
        line = raw.strip()
        if not line:
            if started:
                continue
            started = True
            continue
        if _SUMMARY_STOP_RE.match(line):
            break
        started = True
        if line in seen:
            continue
        seen.add(line)
        files.append(line)
    return files


def collect_job_applied_files(
    *,
    patches_root: Path,
    jobs_root: Path,
    job: Any,
) -> tuple[list[str], str]:
    if str(getattr(job, "status", "")) != "success":
        return [], "non_success"

    issue_id = str(getattr(job, "issue_id", "") or "")
    if issue_id.isdigit():
        diff_rel = _find_latest_artifact_rel(patches_root, "artifacts", f"issue_{issue_id}_diff")
        if diff_rel:
            diff_path = patches_root / diff_rel
            if diff_path.exists() and diff_path.is_file():
                try:
                    with zipfile.ZipFile(diff_path, "r") as zf:
                        files = _parse_diff_manifest(zf.read("manifest.txt"))
                except Exception:
                    files = []
                if files:
                    return files, "diff_manifest"

    log_path = jobs_root / str(getattr(job, "job_id", "")) / "runner.log"
    if log_path.exists() and log_path.is_file():
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            text = ""
        files = _parse_final_summary_files(text)
        if files:
            return files, "final_summary"

    return [], "unavailable"
