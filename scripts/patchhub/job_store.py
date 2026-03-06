from __future__ import annotations

import json
import os
import stat as statlib
from pathlib import Path
from typing import Any


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    try:
        obj = json.loads(raw)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def load_job_json(jobs_root: Path, job_id: str) -> dict[str, Any] | None:
    job_id = str(job_id)
    if not job_id:
        return None
    return _read_json_file(jobs_root / job_id / "job.json")


def _scan_job_dirs_and_sig(jobs_root: Path) -> tuple[tuple[int, int], list[str]]:
    try:
        it = os.scandir(jobs_root)
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return (0, 0), []

    names: list[str] = []
    count = 0
    max_mtime_ns = 0

    with it:
        for ent in it:
            if not ent.is_dir(follow_symlinks=False):
                continue
            name = ent.name
            names.append(name)
            jp = Path(jobs_root) / name / "job.json"
            try:
                st = jp.stat()
            except Exception:
                continue
            if not statlib.S_ISREG(st.st_mode):
                continue
            count += 1
            if int(st.st_mtime_ns) > max_mtime_ns:
                max_mtime_ns = int(st.st_mtime_ns)

    names.sort(reverse=True)
    return (count, max_mtime_ns), names


def iter_job_dirs(jobs_root: Path) -> list[Path]:
    _sig, names = _scan_job_dirs_and_sig(jobs_root)
    return [jobs_root / n for n in names]


# Deterministic in-process cache for on-disk job.json scans.
# Invalidation is signature-based: (count, max mtime_ns) across job.json files.
_LIST_CACHE: dict[str, tuple[tuple[int, int], int, list[dict[str, Any]]]] = {}


def job_json_signature(jobs_root: Path) -> tuple[int, int]:
    """Public signature for on-disk job.json listing invalidation."""
    sig, _names = _scan_job_dirs_and_sig(jobs_root)
    return sig


def list_job_jsons_and_signature(
    jobs_root: Path,
    *,
    limit: int = 200,
) -> tuple[tuple[int, int], list[dict[str, Any]]]:
    limit = max(1, min(int(limit), 2000))
    key = str(jobs_root)

    sig, names = _scan_job_dirs_and_sig(jobs_root)
    cached = _LIST_CACHE.get(key)
    if cached is not None:
        cached_sig, cached_limit, cached_val = cached
        if cached_sig == sig and limit <= cached_limit:
            return sig, list(cached_val[:limit])

    out: list[dict[str, Any]] = []
    for name in names:
        obj = _read_json_file(Path(jobs_root) / name / "job.json")
        if obj is None:
            continue
        out.append(obj)
        if len(out) >= limit:
            break

    _LIST_CACHE[key] = (sig, limit, out)
    return sig, out


def list_job_jsons(jobs_root: Path, *, limit: int = 200) -> list[dict[str, Any]]:
    _sig, out = list_job_jsons_and_signature(jobs_root, limit=limit)
    return out
