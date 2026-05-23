"""Diagnostics emission helpers for import engine.

Engine must remain file_io-only (no core imports) to avoid cross-area
coupling signals. This module contains the required core-facing imports.

ASCII-only.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Protocol, TypeGuard, cast

from audiomason.core import PluginLoader
from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus as _core_get_event_bus
from audiomason.core.jobs.api import JobService
from audiomason.core.jobs.model import JobType
from audiomason.core.jobs.store import JobStore
from audiomason.core.orchestration import Orchestrator
from audiomason.core.process_job_contracts import IMPORT_PROCESS_CONTRACT_ID
from plugins.file_io.service import FileService
from plugins.file_io.service.types import RootName

from .detached_runtime import (
    DetachedImportRuntime,
    load_detached_runtime_bootstrap_from_meta,
    rehydrate_detached_runtime_from_bootstrap,
)
from .file_io_boundary import materialize_root_dir

_METADATA_OPENLIBRARY_TIMEOUT_SECONDS = 2.0


def _builtin_plugins_dir() -> Path:
    plugins_pkg = import_module("plugins")
    pkg_file = plugins_pkg.__file__
    if not isinstance(pkg_file, str) or not pkg_file:
        raise RuntimeError("plugins package path unavailable")
    return Path(pkg_file).resolve().parent


def _user_plugins_dir() -> Path:
    return Path.home() / ".audiomason/plugins"


class _EventBus(Protocol):
    def publish(self, event: str, payload: dict[str, object]) -> None: ...


class _SupportsFileService(Protocol):
    def get_file_service(self) -> FileService: ...


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _to_int_or_default(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _to_float_or_default(value: object, default: float) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _detached_runtime_from_meta(*, job_meta: dict[str, object]) -> DetachedImportRuntime | None:
    try:
        bootstrap = load_detached_runtime_bootstrap_from_meta(job_meta=job_meta)
    except Exception:
        return None
    try:
        return rehydrate_detached_runtime_from_bootstrap(bootstrap=bootstrap)
    except Exception:
        return None


def _jobs_root_from_meta(*, job_meta: dict[str, object]) -> Path | None:
    runtime = _detached_runtime_from_meta(job_meta=job_meta)
    if runtime is None:
        return None
    root_name = RootName.JOBS
    return materialize_root_dir(runtime.get_file_service(), root_name)


def _job_service_for_meta(*, job_meta: dict[str, object]) -> JobService:
    jobs_root = _jobs_root_from_meta(job_meta=job_meta)
    if jobs_root is None:
        return JobService()
    return JobService(store=JobStore(root=jobs_root))


def _job_service_for_engine(*, engine: _SupportsFileService) -> JobService:
    fs = engine.get_file_service()
    root_name = RootName.JOBS
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
    data: dict[str, object],
    required_ctx: dict[str, object] | None,
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
        bus = _get_bus()
        bus.publish(
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


def _get_bus() -> _EventBus:
    # Prefer the import engine test seam when present.
    try:
        engine_mod = import_module("plugins.import.engine")
        fn = cast(object, getattr(engine_mod, "get_event_bus", None))
        if callable(fn):
            get_bus_fn = cast(Callable[[], object], fn)
            bus = get_bus_fn()
            publish = cast(object, getattr(bus, "publish", None))
            if callable(publish):
                return cast(_EventBus, bus)
    except Exception:
        pass
    return cast(_EventBus, _core_get_event_bus())


class _RuntimeImportPlugin:
    def __init__(self, *, engine: _SupportsFileService) -> None:
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


def _plugin_loader(*, engine: _SupportsFileService) -> _ProcessContractPluginLoader:
    loader = _ProcessContractPluginLoader()
    loader.add_plugin("import", _RuntimeImportPlugin(engine=engine))
    return loader


def resolve_import_plugin(*, plugin_name: str) -> object:
    loader = PluginLoader(
        builtin_plugins_dir=_builtin_plugins_dir(),
        user_plugins_dir=_user_plugins_dir(),
    )
    plugin_dir: Path | None = None
    for discovered in loader.discover():
        manifest = loader.load_manifest_only(discovered)
        if manifest.name == plugin_name:
            plugin_dir = discovered
            break
    if plugin_dir is None:
        raise RuntimeError(f"required_process_plugin_not_found:{plugin_name}")

    plugin = loader.load_plugin(plugin_dir, validate=False)
    if plugin_name == "metadata_openlibrary":
        tuned_plugin = cast(_MetadataOpenLibraryTuningPlugin, plugin)
        empty_config: dict[str, object] = {}
        default_max_bytes = _to_int_or_default(
            cast(
                object,
                getattr(
                    plugin,
                    "DEFAULT_MAX_RESPONSE_BYTES",
                    2 * 1024 * 1024,
                ),
            ),
            2 * 1024 * 1024,
        )
        config = _as_str_object_dict(
            cast(
                object,
                getattr(plugin, "config", empty_config),
            )
        )
        config["timeout_seconds"] = _METADATA_OPENLIBRARY_TIMEOUT_SECONDS
        config["max_response_bytes"] = default_max_bytes
        tuned_plugin.config = config
        tuned_plugin.timeout_seconds = _to_float_or_default(
            config.get("timeout_seconds"),
            _METADATA_OPENLIBRARY_TIMEOUT_SECONDS,
        )
        tuned_plugin.max_response_bytes = _to_int_or_default(
            config.get("max_response_bytes"),
            2 * 1024 * 1024,
        )
    return plugin


def _ensure_required_process_plugins(*, loader: _ProcessContractPluginLoader) -> None:
    for plugin_name in ("audio_processor", "cover_handler", "id3_tagger"):
        loader.add_plugin(
            plugin_name,
            resolve_import_plugin(plugin_name=plugin_name),
        )


def build_process_contract_plugin_loader(
    *, job_meta: dict[str, object]
) -> _ProcessContractPluginLoader:
    runtime = _detached_runtime_from_meta(job_meta=job_meta)
    if runtime is None:
        raise RuntimeError("detached process runtime bootstrap is required")
    loader = _plugin_loader(engine=runtime)
    _ensure_required_process_plugins(loader=loader)
    return loader


def start_process_runtime(*, engine: _SupportsFileService | None = None) -> None:
    try:
        if engine is None:
            Orchestrator().start_process_runtime()
        else:
            orch = Orchestrator(job_service=_job_service_for_engine(engine=engine))
            orch.start_process_runtime()
    except Exception:
        return


def create_process_job(*, meta: dict[str, object]) -> str:
    """Create a PROCESS job and return job_id.

    This is a thin core-facing facade to keep core imports out of engine.py.
    """

    payload = dict(meta)
    payload.setdefault("contract_id", IMPORT_PROCESS_CONTRACT_ID)
    service = _job_service_for_meta(job_meta=payload)
    payload_meta = {key: str(value) for key, value in payload.items()}
    job = service.create_job(JobType.PROCESS, meta=payload_meta)
    _link_job_alias(job_id=str(job.job_id), primary=service)
    return str(job.job_id)


def submit_process_job(*, engine: _SupportsFileService, job_id: str, verbosity: int = 1) -> None:
    """Submit an existing PROCESS job through core orchestration."""

    orch = Orchestrator(job_service=_job_service_for_engine(engine=engine))
    orch.submit_process_contract_job(job_id, verbosity=verbosity)
