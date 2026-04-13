"""Import-owned metadata validation boundary adapter.

ASCII-only.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol, cast

from audiomason.core.config_service import ConfigService
from audiomason.core.errors import PluginNotFoundError
from audiomason.core.loader import PluginLoader
from audiomason.core.orchestration import _run_coro_sync
from audiomason.core.plugin_callable_authority import (
    RegisteredWizardCallable,
    resolve_registered_wizard_callable,
)
from audiomason.core.plugin_registry import PluginRegistry

_DEFAULT_AUTHOR = {"valid": False, "canonical": None, "suggestion": None}
_DEFAULT_BOOK = {"valid": False, "canonical": None, "suggestion": None}
_DEFAULT_RESULT = {
    "provider": "metadata_openlibrary",
    "author": dict(_DEFAULT_AUTHOR),
    "book": dict(_DEFAULT_BOOK),
}


class _Phase1ValidationJobBuilder(Protocol):
    def __call__(self, author: str, title: str) -> dict[str, Any]: ...


class _MetadataPhase1ValidationPlugin(Protocol):
    DEFAULT_MAX_RESPONSE_BYTES: int
    config: dict[str, object]
    timeout_seconds: float
    max_response_bytes: int

    async def execute_job(self, job: dict[str, Any]) -> dict[str, Any]: ...


def _builtin_plugins_dir() -> Path:
    plugins_pkg = import_module("plugins")
    pkg_file = getattr(plugins_pkg, "__file__", None)
    if not isinstance(pkg_file, str) or not pkg_file:
        raise RuntimeError("plugins package path unavailable")
    return Path(pkg_file).resolve().parent


@lru_cache(maxsize=1)
def _callable_authority() -> tuple[PluginRegistry, PluginLoader]:
    registry = PluginRegistry(ConfigService())
    loader = PluginLoader(
        builtin_plugins_dir=_builtin_plugins_dir(),
        registry=registry,
    )
    return registry, loader


def _tune_metadata_plugin(
    plugin: _MetadataPhase1ValidationPlugin,
) -> _MetadataPhase1ValidationPlugin:
    default_max_bytes = getattr(plugin, "DEFAULT_MAX_RESPONSE_BYTES", 2 * 1024 * 1024)
    config = dict(getattr(plugin, "config", {}) or {})
    config["timeout_seconds"] = 0.1
    try:
        config["max_response_bytes"] = int(default_max_bytes)
    except (TypeError, ValueError):
        config["max_response_bytes"] = 2 * 1024 * 1024
    plugin.config = config
    try:
        plugin.timeout_seconds = float(config["timeout_seconds"])
    except (TypeError, ValueError):
        plugin.timeout_seconds = 0.1
    try:
        plugin.max_response_bytes = int(config["max_response_bytes"])
    except (TypeError, ValueError):
        plugin.max_response_bytes = 2 * 1024 * 1024
    return plugin


def _resolve_phase1_validation_authority() -> tuple[
    _Phase1ValidationJobBuilder,
    _MetadataPhase1ValidationPlugin,
]:
    registry, loader = _callable_authority()
    published = registry.resolve_wizard_callable(
        "metadata.phase1_validate",
        loader=loader,
    )
    if published.execution_mode != "job":
        raise RuntimeError(
            "wizard_callable_execution_mode_mismatch:"
            f"metadata.phase1_validate:{published.execution_mode}"
        )
    try:
        plugin_any = loader.get_plugin(published.plugin_id)
    except PluginNotFoundError:
        plugin_any = loader.load_plugin(published.manifest_path.parent, validate=False)
    plugin = _tune_metadata_plugin(cast(_MetadataPhase1ValidationPlugin, plugin_any))
    callable_def = RegisteredWizardCallable(
        plugin_id=published.plugin_id,
        plugin_dir=published.manifest_path.parent,
        manifest_path=published.manifest_path,
        operation_id=published.operation_id,
        method_name=published.method_name,
        execution_mode=published.execution_mode,
    )
    build_job = cast(
        _Phase1ValidationJobBuilder,
        resolve_registered_wizard_callable(
            plugin_obj=plugin,
            callable_def=callable_def,
        ),
    )
    return build_job, plugin


def _run_phase1_validation_job(
    *,
    job: dict[str, Any],
    plugin: _MetadataPhase1ValidationPlugin,
) -> dict[str, Any]:
    result_box = {"result": dict(_DEFAULT_RESULT)}

    async def _runner() -> None:
        result = await plugin.execute_job(dict(job))
        if isinstance(result, dict):
            result_box["result"] = dict(result)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            _run_coro_sync(_runner())
        except Exception:
            return dict(_DEFAULT_RESULT)
        return dict(result_box["result"])
    return dict(_DEFAULT_RESULT)


def _validate_author_title_payload(author: str, title: str) -> dict[str, Any]:
    if not author or not title:
        return dict(_DEFAULT_RESULT)
    try:
        build_job, plugin = _resolve_phase1_validation_authority()
        job = build_job(author, title)
        if not isinstance(job, dict):
            return dict(_DEFAULT_RESULT)
        result = _run_phase1_validation_job(job=dict(job), plugin=plugin)
    except Exception:
        return dict(_DEFAULT_RESULT)
    if not isinstance(result, dict):
        return dict(_DEFAULT_RESULT)
    author_payload = result.get("author")
    book_payload = result.get("book")
    author_result = (
        dict(author_payload) if isinstance(author_payload, dict) else dict(_DEFAULT_AUTHOR)
    )
    book_result = dict(book_payload) if isinstance(book_payload, dict) else dict(_DEFAULT_BOOK)
    return {
        "provider": str(result.get("provider") or "metadata_openlibrary"),
        "author": author_result,
        "book": book_result,
    }


@lru_cache(maxsize=128)
def validate_author_title(
    author: str,
    title: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = _validate_author_title_payload(author, title)
    return dict(result["author"]), dict(result["book"])


__all__ = ["validate_author_title"]
