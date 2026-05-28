"""Core-facing processed registry integration for the import plugin.

Subscribes to diagnostics events and updates the processed registry when
import-generated PROCESS jobs succeed.

This module intentionally avoids importing multiple external areas directly.

ASCII-only.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeGuard, cast

from plugins.file_io.service import FileService
from plugins.file_io.service.types import RootName

from . import core_facade, file_io_facade
from .detached_runtime import (
    load_detached_runtime_bootstrap_from_meta,
    rehydrate_detached_runtime_from_bootstrap,
)
from .file_io_boundary import materialize_root_dir
from .process_contract_completion import (
    apply_successful_process_completion,
    successful_process_completion_already_applied,
)
from .storage import read_json

_installed = False
_registered_file_services: list[FileService] = []
# Backward-compatible globals used by tests and older code paths.
_INSTALLED: bool = False
_REGISTERED_FILE_SERVICES: list[FileService] = _registered_file_services


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _set_installed_compat(value: bool) -> None:
    compat_globals = cast(dict[str, object], globals())
    compat_globals["_INSTALLED"] = value


def _file_service_signature(fs: FileService) -> tuple[tuple[str, str], ...]:
    items: list[tuple[str, str]] = []
    for root_name in sorted(file_io_facade.ROOT_MAP):
        root = file_io_facade.ROOT_MAP[root_name]
        items.append((root_name, str(materialize_root_dir(fs, root))))
    return tuple(items)


def _register_file_service(fs: FileService) -> None:
    sig = _file_service_signature(fs)
    for existing in _registered_file_services:
        if _file_service_signature(existing) == sig:
            return
    _registered_file_services.append(fs)


def _file_service_from_detached_runtime(job_meta: dict[str, object]) -> FileService | None:
    try:
        bootstrap = load_detached_runtime_bootstrap_from_meta(job_meta=job_meta)
    except Exception:
        return None
    runtime = rehydrate_detached_runtime_from_bootstrap(bootstrap=bootstrap)
    if runtime is None:
        return None
    return runtime.get_file_service()


def _match_score(*, job_meta: dict[str, object], job_requests: dict[str, object]) -> int:
    diagnostics = _as_str_object_dict(job_requests.get("diagnostics_context"))

    score = 0

    def _require(meta_key: str, actual: object) -> bool:
        nonlocal score
        expected = str(job_meta.get(meta_key) or "").strip()
        if not expected:
            return True
        actual_text = str(actual or "").strip()
        if not actual_text or actual_text != expected:
            return False
        score += 1
        return True

    if not _require("session_id", job_requests.get("session_id")):
        return -1
    if not _require("idempotency_key", job_requests.get("idempotency_key")):
        return -1
    if not _require("effective_config_fingerprint", job_requests.get("config_fingerprint")):
        return -1
    if not _require("model_fingerprint", diagnostics.get("model_fingerprint")):
        return -1
    if not _require("discovery_fingerprint", diagnostics.get("discovery_fingerprint")):
        return -1
    return score


def _candidate_from_registered_file_services(
    *,
    job_meta: dict[str, object],
    root: RootName,
    rel_path: str,
) -> tuple[FileService, dict[str, object]] | None:
    matches: list[tuple[int, FileService, dict[str, object]]] = []
    for fs in _registered_file_services:
        if not fs.exists(root, rel_path):
            continue
        try:
            job_requests_any = read_json(fs, root, rel_path)
        except Exception:
            continue
        if not _is_str_object_dict(job_requests_any):
            continue
        if len(_registered_file_services) == 1:
            return fs, job_requests_any
        score = _match_score(job_meta=job_meta, job_requests=job_requests_any)
        if score < 0:
            continue
        matches.append((score, fs, job_requests_any))

    if len(matches) == 1:
        _score, fs, job_requests = matches[0]
        return fs, job_requests

    if not matches:
        return None

    best_score = max(score for score, _fs, _job_requests in matches)
    if best_score <= 0:
        return None

    best = [item for item in matches if item[0] == best_score]
    if len(best) != 1:
        return None

    _score, fs, job_requests = best[0]
    return fs, job_requests


def _install_processed_registry_subscriber_impl(*, resolver: object) -> None:
    """Install the processed registry subscriber (idempotent)."""

    global _installed, _INSTALLED
    _installed = _INSTALLED
    fs = file_io_facade.file_service_from_resolver(resolver)
    _register_file_service(fs)
    if _installed:
        return

    def _on_any(event: str, payload: dict[str, object]) -> None:
        if event != "diag.job.end":
            return

        data_any = payload.get("data")
        if not _is_str_object_dict(data_any):
            return

        if data_any.get("status") != "succeeded":
            return

        job_id = data_any.get("job_id")
        job_type = data_any.get("job_type")
        if job_type != "process":
            return
        if not isinstance(job_id, str) or not job_id:
            return

        job = core_facade.get_job_service().get_job(job_id)
        meta = _as_str_object_dict(job.meta)
        if meta.get("source") != "import":
            return

        jr_path = meta.get("job_requests_path")
        if not isinstance(jr_path, str) or ":" not in jr_path:
            return

        root_str, rel_path = jr_path.split(":", 1)
        root_str = root_str.strip()
        rel_path = rel_path.strip().lstrip("/")
        if not root_str or not rel_path:
            return

        root = file_io_facade.ROOT_MAP.get(str(root_str))
        if root is None:
            return

        selected = None
        detached_fs = _file_service_from_detached_runtime(meta)
        if detached_fs is not None:
            try:
                job_requests_any = read_json(detached_fs, root, rel_path)
            except Exception:
                return
            if not _is_str_object_dict(job_requests_any):
                return
            selected = (detached_fs, job_requests_any)
        else:
            selected = _candidate_from_registered_file_services(
                job_meta=meta,
                root=root,
                rel_path=rel_path,
            )
            if selected is None:
                return

        selected_fs, job_requests_any = selected
        if successful_process_completion_already_applied(
            fs=selected_fs,
            job_id=job_id,
            job_requests=job_requests_any,
        ):
            return

        apply_successful_process_completion(
            fs=selected_fs,
            job_id=job_id,
            job_requests=job_requests_any,
        )

    bus = core_facade.get_bus()
    subscribe_all = cast(object, getattr(bus, "subscribe_all", None))
    if not callable(subscribe_all):
        return
    cast(Callable[[Callable[[str, dict[str, object]], None]], None], subscribe_all)(_on_any)
    _installed = True
    _set_installed_compat(True)


def install_processed_registry_subscriber(*, resolver: object) -> None:
    """Install processed-registry subscriber via compatibility hook."""

    _install_processed_registry_subscriber(resolver=resolver)


def _install_processed_registry_subscriber(*, resolver: object) -> None:
    _install_processed_registry_subscriber_impl(resolver=resolver)
