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


def list_job_jsons(jobs_root: Path, *, limit: int = 200) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 2000))
    out: list[dict[str, Any]] = []
    for d in iter_job_dirs(jobs_root):
        obj = _read_json_file(d / "job.json")
        if obj is None:
            continue
        out.append(obj)
        if len(out) >= limit:
            break
    return out
