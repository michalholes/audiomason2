"""Detached phase-2 runtime bootstrap for canonical import job requests.

ASCII-only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeGuard, cast

from plugins.file_io.import_runtime import normalize_relative_path
from plugins.file_io.service import FileService
from plugins.file_io.service.types import RootName

from .file_io_boundary import materialize_root_dir
from .storage import read_json

_ROOT_KEYS: tuple[tuple[RootName, str], ...] = (
    (RootName.INBOX, "inbox_dir"),
    (RootName.STAGE, "stage_dir"),
    (RootName.JOBS, "jobs_dir"),
    (RootName.OUTBOX, "outbox_dir"),
    (RootName.CONFIG, "config_dir"),
    (RootName.WIZARDS, "wizards_dir"),
)


class _SupportsFileService(Protocol):
    def get_file_service(self) -> FileService: ...


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


@dataclass(frozen=True)
class DetachedImportRuntime:
    """Minimal phase-2 runtime rehydrated from canonical job_requests.json."""

    _fs: FileService

    def get_file_service(self) -> FileService:
        return self._fs


def build_detached_runtime_bootstrap(*, fs: FileService) -> dict[str, object]:
    roots: dict[str, str] = {}
    for root_name, key in _ROOT_KEYS:
        roots[key] = str(materialize_root_dir(fs, root_name))
    return {
        "version": 1,
        "file_io": {
            "roots": roots,
        },
    }


def serialize_detached_runtime_bootstrap(*, fs: FileService) -> str:
    return json.dumps(
        build_detached_runtime_bootstrap(fs=fs),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _parse_job_requests_path(text: str) -> tuple[RootName, str]:
    root_text, rel_path = text.split(":", 1)
    root = RootName(root_text.strip())
    rel = normalize_relative_path(rel_path.strip())
    if not rel:
        raise ValueError("job_requests_path must include a relative path")
    return root, rel


def load_canonical_job_requests(
    *, fs: FileService, job_meta: dict[str, object]
) -> dict[str, object]:
    job_requests_path = str(job_meta.get("job_requests_path") or "")
    if not job_requests_path:
        raise ValueError("job_requests_path is required")
    root, rel_path = _parse_job_requests_path(job_requests_path)
    loaded = read_json(fs, root, rel_path)
    if not _is_str_object_dict(loaded):
        raise ValueError("job_requests.json is invalid")
    return loaded


def _bootstrap_roots(job_requests: dict[str, object]) -> dict[RootName, Path] | None:
    runtime = _as_str_object_dict(job_requests.get("detached_runtime"))
    if not runtime:
        return None

    file_io = _as_str_object_dict(runtime.get("file_io"))
    roots_doc = _as_str_object_dict(file_io.get("roots"))
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


def rehydrate_detached_runtime_from_bootstrap(
    *, bootstrap: dict[str, object]
) -> DetachedImportRuntime | None:
    roots = _bootstrap_roots({"detached_runtime": bootstrap})
    if roots is None:
        return None
    return DetachedImportRuntime(FileService(roots))


def rehydrate_detached_runtime(*, job_requests: dict[str, object]) -> DetachedImportRuntime | None:
    runtime = _as_str_object_dict(job_requests.get("detached_runtime"))
    return rehydrate_detached_runtime_from_bootstrap(bootstrap=runtime)


def load_detached_runtime_bootstrap_from_meta(*, job_meta: dict[str, object]) -> dict[str, object]:
    raw = str(job_meta.get("detached_runtime_json") or "")
    if not raw:
        raise ValueError("detached_runtime_json is required")
    loaded = cast(object, json.loads(raw))
    if not _is_str_object_dict(loaded):
        raise ValueError("detached_runtime_json is invalid")
    return loaded


def resolve_phase2_runtime(
    *, live_engine: _SupportsFileService, job_meta: dict[str, object]
) -> DetachedImportRuntime | _SupportsFileService:
    fs = live_engine.get_file_service()
    job_requests = load_canonical_job_requests(fs=fs, job_meta=job_meta)
    detached = rehydrate_detached_runtime(job_requests=job_requests)
    if detached is not None:
        return detached
    return live_engine
