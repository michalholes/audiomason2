from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
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


def iter_job_dirs(jobs_root: Path) -> list[Path]:
    if not jobs_root.exists() or not jobs_root.is_dir():
        return []
    out: list[Path] = []
    for p in jobs_root.iterdir():
        if p.is_dir():
            out.append(p)
    out.sort(key=lambda x: x.name, reverse=True)
    return out


# Deterministic in-process cache for on-disk job.json scans.
# Invalidation is signature-based: (count, max mtime_ns) across job.json files.
_LIST_CACHE: dict[str, tuple[tuple[int, int], int, list[dict[str, Any]]]] = {}


def _job_json_signature(jobs_root: Path) -> tuple[int, int]:
    if not jobs_root.exists() or not jobs_root.is_dir():
        return (0, 0)
    count = 0
    max_mtime_ns = 0
    for d in jobs_root.iterdir():
        if not d.is_dir():
            continue
        jp = d / "job.json"
        if not jp.exists() or not jp.is_file():
            continue
        try:
            st = jp.stat()
        except Exception:
            continue
        count += 1
        if st.st_mtime_ns > max_mtime_ns:
            max_mtime_ns = st.st_mtime_ns
    return (count, max_mtime_ns)


def list_job_jsons(jobs_root: Path, *, limit: int = 200) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 2000))
    key = str(jobs_root)

    sig = _job_json_signature(jobs_root)
    cached = _LIST_CACHE.get(key)
    if cached is not None:
        cached_sig, cached_limit, cached_val = cached
        if cached_sig == sig and limit <= cached_limit:
            return list(cached_val[:limit])

    out: list[dict[str, Any]] = []
    for d in iter_job_dirs(jobs_root):
        obj = _read_json_file(d / "job.json")
        if obj is None:
            continue
        out.append(obj)
        if len(out) >= limit:
            break

    _LIST_CACHE[key] = (sig, limit, out)
    return out
