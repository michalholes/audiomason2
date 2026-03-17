"""Detached phase-2 runtime bootstrap for canonical import job requests.

ASCII-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plugins.file_io.import_runtime import normalize_relative_path
from plugins.file_io.service import FileService
from plugins.file_io.service.types import RootName

from .storage import read_json

_ROOT_KEYS: tuple[tuple[RootName, str], ...] = (
    (RootName.INBOX, "inbox_dir"),
    (RootName.STAGE, "stage_dir"),
    (RootName.JOBS, "jobs_dir"),
    (RootName.OUTBOX, "outbox_dir"),
    (RootName.CONFIG, "config_dir"),
    (RootName.WIZARDS, "wizards_dir"),
)


@dataclass(frozen=True)
class DetachedImportRuntime:
    """Minimal phase-2 runtime rehydrated from canonical job_requests.json."""

    _fs: FileService

    def get_file_service(self) -> FileService:
        return self._fs


def build_detached_runtime_bootstrap(*, fs: FileService) -> dict[str, Any]:
    roots: dict[str, str] = {}
    for root_name, key in _ROOT_KEYS:
        roots[key] = str(fs.root_dir(root_name))
    return {
        "version": 1,
        "file_io": {
            "roots": roots,
        },
    }


def _parse_job_requests_path(text: str) -> tuple[RootName, str]:
    root_text, rel_path = text.split(":", 1)
    root = RootName(root_text.strip())
    rel = normalize_relative_path(rel_path.strip())
    if not rel:
        raise ValueError("job_requests_path must include a relative path")
    return root, rel


def load_canonical_job_requests(*, fs: FileService, job_meta: dict[str, Any]) -> dict[str, Any]:
    job_requests_path = str(job_meta.get("job_requests_path") or "")
    if not job_requests_path:
        raise ValueError("job_requests_path is required")
    root, rel_path = _parse_job_requests_path(job_requests_path)
    loaded = read_json(fs, root, rel_path)
    if not isinstance(loaded, dict):
        raise ValueError("job_requests.json is invalid")
    return loaded


def _bootstrap_roots(job_requests: dict[str, Any]) -> dict[RootName, Path] | None:
    runtime_any = job_requests.get("detached_runtime")
    runtime = dict(runtime_any) if isinstance(runtime_any, dict) else {}
    if not runtime:
        return None

    file_io_any = runtime.get("file_io")
    file_io = dict(file_io_any) if isinstance(file_io_any, dict) else {}
    roots_any = file_io.get("roots")
    roots_doc = dict(roots_any) if isinstance(roots_any, dict) else {}
    if not roots_doc:
        raise ValueError("detached_runtime.file_io.roots is required")

    roots: dict[RootName, Path] = {}
    missing: list[str] = []
    for root_name, key in _ROOT_KEYS:
        path_text = str(roots_doc.get(key) or "").strip()
        if not path_text:
            missing.append(key)
            continue
        roots[root_name] = Path(path_text).expanduser()

    if missing:
        raise ValueError(
            "detached_runtime.file_io.roots missing required keys: " + ", ".join(sorted(missing))
        )
    return roots


def rehydrate_detached_runtime(*, job_requests: dict[str, Any]) -> DetachedImportRuntime | None:
    roots = _bootstrap_roots(job_requests)
    if roots is None:
        return None
    return DetachedImportRuntime(FileService(roots))


def resolve_phase2_runtime(*, live_engine: Any, job_meta: dict[str, Any]) -> Any:
    fs = live_engine.get_file_service()
    job_requests = load_canonical_job_requests(fs=fs, job_meta=job_meta)
    detached = rehydrate_detached_runtime(job_requests=job_requests)
    if detached is not None:
        return detached
    return live_engine
