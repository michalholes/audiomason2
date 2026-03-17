"""Diagnostics emission helpers for import engine.

Engine must remain file_io-only (no core imports) to avoid cross-area
coupling signals. This module contains the required core-facing imports.

ASCII-only.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any, cast

from audiomason.core.diagnostics import build_envelope
from audiomason.core.errors import PluginNotFoundError
from audiomason.core.events import get_event_bus as _core_get_event_bus
from audiomason.core.jobs.api import JobService
from audiomason.core.jobs.model import JobType
from audiomason.core.loader import PluginLoader
from audiomason.core.orchestration import Orchestrator
from audiomason.core.process_job_contracts import IMPORT_PROCESS_CONTRACT_ID


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


def _builtin_plugins_root() -> Path:
    plugins_pkg = import_module("plugins")
    pkg_file = getattr(plugins_pkg, "__file__", None)
    if not isinstance(pkg_file, str) or not pkg_file:
        raise RuntimeError("plugins package path unavailable")
    return Path(pkg_file).resolve().parent


def _user_plugins_root() -> Path:
    return Path.home() / ".audiomason/plugins"


class _ImportProcessRuntimePlugin:
    def __init__(self, *, engine: object) -> None:
        self._engine = engine

    async def run_process_contract(
        self, *, job_id: str, job_meta: dict[str, object], plugin_loader: object
    ) -> None:
        from .phase2_job_runner import run_phase2_job_requests

        await run_phase2_job_requests(
            engine=self._engine,
            job_id=job_id,
            job_meta=dict(job_meta),
            plugin_loader=plugin_loader,
        )


_REQUIRED_PROCESS_PLUGINS = ("audio_processor", "cover_handler", "id3_tagger")


def _plugin_loader(*, engine: object) -> PluginLoader:
    loader = PluginLoader(
        builtin_plugins_dir=_builtin_plugins_root(),
        user_plugins_dir=_user_plugins_root(),
        registry=None,
    )
    loader._plugins["import"] = _ImportProcessRuntimePlugin(engine=engine)
    return loader


def _ensure_required_process_plugins(*, loader: object) -> None:
    loader_any = cast(Any, loader)
    builtin_dir = getattr(loader_any, "builtin_plugins_dir", None)
    if builtin_dir is None:
        raise RuntimeError("plugin loader missing builtin_plugins_dir")

    builtin_root = Path(builtin_dir)
    for plugin_name in _REQUIRED_PROCESS_PLUGINS:
        try:
            loader_any.get_plugin(plugin_name)
        except PluginNotFoundError as exc:
            plugin_dir = builtin_root / plugin_name
            if not (plugin_dir / "plugin.yaml").exists():
                raise RuntimeError(f"required process plugin not found: {plugin_name}") from exc
            loader_any.load_plugin(plugin_dir, validate=False)


def create_process_job(*, meta: dict[str, Any]) -> str:
    """Create a PROCESS job and return job_id.

    This is a thin core-facing facade to keep core imports out of engine.py.
    """

    payload = dict(meta)
    payload.setdefault("contract_id", IMPORT_PROCESS_CONTRACT_ID)
    job = JobService().create_job(JobType.PROCESS, meta=payload)
    return str(job.job_id)


def submit_process_job(*, engine: object, job_id: str, verbosity: int = 1) -> None:
    """Submit an existing PROCESS job through core orchestration."""

    loader = _plugin_loader(engine=engine)
    _ensure_required_process_plugins(loader=loader)
    Orchestrator().run_job(job_id, plugin_loader=loader, verbosity=verbosity)
