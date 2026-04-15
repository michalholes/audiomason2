"""Diagnostics emission helpers for import engine.

Engine must remain file_io-only (no core imports) to avoid cross-area
coupling signals. This module contains the required core-facing imports.

ASCII-only.
"""

from __future__ import annotations

import shutil
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol, cast

from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus as _core_get_event_bus
from audiomason.core.jobs.api import JobService
from audiomason.core.jobs.model import JobType
from audiomason.core.jobs.store import JobStore
from audiomason.core.orchestration import Orchestrator
from audiomason.core.process_contract_authority import _ContractPluginLoader
from audiomason.core.process_job_contracts import IMPORT_PROCESS_CONTRACT_ID

from .detached_runtime import (
    DetachedImportRuntime,
    load_detached_runtime_bootstrap_from_meta,
    rehydrate_detached_runtime_from_bootstrap,
)
from .file_io_boundary import materialize_root_dir

_METADATA_OPENLIBRARY_TIMEOUT_SECONDS = 2.0


def _detached_runtime_from_meta(*, job_meta: dict[str, Any]) -> DetachedImportRuntime | None:
    try:
        bootstrap = load_detached_runtime_bootstrap_from_meta(job_meta=job_meta)
    except Exception:
        return None
    try:
        return rehydrate_detached_runtime_from_bootstrap(bootstrap=bootstrap)
    except Exception:
        return None


def _jobs_root_from_meta(*, job_meta: dict[str, Any]) -> Path | None:
    runtime = _detached_runtime_from_meta(job_meta=job_meta)
    if runtime is None:
        return None
    root_name = import_module("plugins.file_io.service").RootName.JOBS
    return materialize_root_dir(runtime.get_file_service(), root_name)


def _job_service_for_meta(*, job_meta: dict[str, Any]) -> JobService:
    jobs_root = _jobs_root_from_meta(job_meta=job_meta)
    if jobs_root is None:
        return JobService()
    return JobService(store=JobStore(root=jobs_root))


def _job_service_for_engine(*, engine: object) -> JobService:
    fs = cast(Any, engine).get_file_service()
    root_name = import_module("plugins.file_io.service").RootName.JOBS
    return JobService(store=JobStore(root=materialize_root_dir(fs, root_name)))


def _link_job_alias(*, job_id: str, primary: JobService) -> None:
    alias = JobService()
    alias_root = alias.store.root
    primary_root = primary.store.root
    if alias_root == primary_root:
        return
    alias_root.mkdir(parents=True, exist_ok=True)
    alias_dir = alias.store.job_dir(job_id)
    primary_dir = primary.store.job_dir(job_id)
    if not primary_dir.exists():
        return
    if alias_dir.is_symlink():
        try:
            if alias_dir.resolve() == primary_dir.resolve():
                return
        except OSError:
            pass
        alias_dir.unlink(missing_ok=True)
    elif alias_dir.exists():
        shutil.rmtree(alias_dir)
    try:
        alias_dir.symlink_to(primary_dir, target_is_directory=True)
    except OSError:
        return


def emit_required(
    *,
    event: str,
    operation: str,
    data: dict[str, Any],
    required_ctx: dict[str, Any] | None,
) -> None:
    """Emit diagnostics with required context fields.

    required_ctx must contain (when available):
      - session_id
      - model_fingerprint
      - discovery_fingerprint
      - effective_config_fingerprint

    Emission is fail-safe.
    """

    payload = dict(data)
    ctx = required_ctx or {}
    for key in [
        "session_id",
        "model_fingerprint",
        "discovery_fingerprint",
        "effective_config_fingerprint",
    ]:
        if key in ctx:
            payload[key] = ctx[key]

    try:
        _get_bus().publish(
            event,
            build_envelope(
                event=event,
                component="import",
                operation=operation,
                data=payload,
            ),
        )
    except Exception:
        return


def _get_bus():
    # Prefer the import engine test seam when present.
    try:
        engine_mod = import_module("plugins.import.engine")
        fn = getattr(engine_mod, "get_event_bus", None)
        if callable(fn):
            return fn()
    except Exception:
        pass
    return _core_get_event_bus()


class _RuntimeImportPlugin:
    def __init__(self, *, engine: object) -> None:
        self._engine = engine

    async def run_process_contract(
        self, *, job_id: str, job_meta: dict[str, object], plugin_loader: object
    ) -> None:
        from .process_contract_completion import run_process_contract_completion

        await run_process_contract_completion(
            engine=self._engine,
            job_id=job_id,
            job_meta=dict(job_meta),
            plugin_loader=plugin_loader,
        )


_ImportProcessRuntimePlugin = _RuntimeImportPlugin


class _MetadataOpenLibraryTuningPlugin(Protocol):
    DEFAULT_MAX_RESPONSE_BYTES: int
    config: dict[str, object]
    timeout_seconds: float
    max_response_bytes: int


class _ProcessContractPluginLoader:
    def __init__(self, plugins: dict[str, object] | None = None) -> None:
        self._plugins: dict[str, object] = dict(plugins or {})

    def add_plugin(self, name: str, plugin: object) -> None:
        self._plugins[name] = plugin

    def get_plugin(self, name: str) -> object:
        return self._plugins[name]

    def list_plugins(self) -> list[str]:
        return list(self._plugins.keys())


def _plugin_loader(*, engine: object) -> _ProcessContractPluginLoader:
    loader = _ProcessContractPluginLoader()
    loader.add_plugin("import", _RuntimeImportPlugin(engine=engine))
    return loader


def resolve_import_plugin(*, plugin_name: str) -> object:
    loader = _ContractPluginLoader(job_meta={}, contract_plugin_name=plugin_name)
    plugin = loader.get_plugin(plugin_name)
    if plugin_name == "metadata_openlibrary":
        tuned_plugin = cast(_MetadataOpenLibraryTuningPlugin, plugin)
        default_max_bytes = getattr(
            plugin,
            "DEFAULT_MAX_RESPONSE_BYTES",
            2 * 1024 * 1024,
        )
        config = dict(getattr(plugin, "config", {}) or {})
        config["timeout_seconds"] = _METADATA_OPENLIBRARY_TIMEOUT_SECONDS
        try:
            config["max_response_bytes"] = int(default_max_bytes)
        except (TypeError, ValueError):
            config["max_response_bytes"] = 2 * 1024 * 1024
        tuned_plugin.config = config
        try:
            tuned_plugin.timeout_seconds = float(config["timeout_seconds"])
        except (TypeError, ValueError):
            tuned_plugin.timeout_seconds = _METADATA_OPENLIBRARY_TIMEOUT_SECONDS
        try:
            tuned_plugin.max_response_bytes = int(config["max_response_bytes"])
        except (TypeError, ValueError):
            tuned_plugin.max_response_bytes = 2 * 1024 * 1024
    return plugin


def _ensure_required_process_plugins(*, loader: _ProcessContractPluginLoader) -> None:
    for plugin_name in ("audio_processor", "cover_handler", "id3_tagger"):
        loader.add_plugin(
            plugin_name,
            resolve_import_plugin(plugin_name=plugin_name),
        )


def build_process_contract_plugin_loader(
    *, job_meta: dict[str, Any]
) -> _ProcessContractPluginLoader:
    runtime = _detached_runtime_from_meta(job_meta=job_meta)
    if runtime is None:
        raise RuntimeError("detached process runtime bootstrap is required")
    loader = _plugin_loader(engine=runtime)
    _ensure_required_process_plugins(loader=loader)
    return loader


def start_process_runtime(*, engine: object | None = None) -> None:
    try:
        if engine is None:
            Orchestrator().start_process_runtime()
        else:
            orch = Orchestrator(job_service=_job_service_for_engine(engine=engine))
            orch.start_process_runtime()
    except Exception:
        return


def create_process_job(*, meta: dict[str, Any]) -> str:
    """Create a PROCESS job and return job_id.

    This is a thin core-facing facade to keep core imports out of engine.py.
    """

    payload = dict(meta)
    payload.setdefault("contract_id", IMPORT_PROCESS_CONTRACT_ID)
    service = _job_service_for_meta(job_meta=payload)
    job = service.create_job(JobType.PROCESS, meta=payload)
    _link_job_alias(job_id=str(job.job_id), primary=service)
    return str(job.job_id)


def submit_process_job(*, engine: object, job_id: str, verbosity: int = 1) -> None:
    """Submit an existing PROCESS job through core orchestration."""

    orch = Orchestrator(job_service=_job_service_for_engine(engine=engine))
    orch.submit_process_contract_job(job_id, verbosity=verbosity)
