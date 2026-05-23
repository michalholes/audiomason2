"""Import-owned metadata validation boundary adapter.

ASCII-only.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol, TypeGuard, cast

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
_PHASE1_METADATA_TIMEOUT_SECONDS = 2.0


class _Phase1ValidationJobBuilder(Protocol):
    def __call__(self, author: str, title: str) -> dict[str, object]: ...


class _MetadataPhase1ValidationPlugin(Protocol):
    DEFAULT_MAX_RESPONSE_BYTES: int
    config: dict[str, object]
    timeout_seconds: float
    max_response_bytes: int

    async def execute_job(self, job: dict[str, object]) -> dict[str, object]: ...


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


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


def _builtin_plugins_dir() -> Path:
    return Path(__file__).resolve().parents[1]


_CALLABLE_AUTHORITY: tuple[PluginRegistry, PluginLoader] | None = None


def _callable_authority() -> tuple[PluginRegistry, PluginLoader]:
    global _CALLABLE_AUTHORITY
    if _CALLABLE_AUTHORITY is None:
        registry = PluginRegistry(ConfigService())
        loader = PluginLoader(
            builtin_plugins_dir=_builtin_plugins_dir(),
            registry=registry,
        )
        _CALLABLE_AUTHORITY = (registry, loader)
    return _CALLABLE_AUTHORITY


def _tune_metadata_plugin(
    plugin: _MetadataPhase1ValidationPlugin,
) -> _MetadataPhase1ValidationPlugin:
    empty_config: dict[str, object] = {}
    default_max_bytes = _to_int_or_default(
        cast(object, getattr(plugin, "DEFAULT_MAX_RESPONSE_BYTES", 2 * 1024 * 1024)),
        2 * 1024 * 1024,
    )
    config = _as_str_object_dict(cast(object, getattr(plugin, "config", empty_config)))
    config["timeout_seconds"] = _PHASE1_METADATA_TIMEOUT_SECONDS
    config["max_response_bytes"] = default_max_bytes
    plugin.config = config
    plugin.timeout_seconds = _to_float_or_default(
        config.get("timeout_seconds"),
        _PHASE1_METADATA_TIMEOUT_SECONDS,
    )
    plugin.max_response_bytes = _to_int_or_default(
        config.get("max_response_bytes"),
        2 * 1024 * 1024,
    )
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
    job: dict[str, object],
    plugin: _MetadataPhase1ValidationPlugin,
) -> dict[str, object]:
    result_box: dict[str, dict[str, object]] = {"result": dict(_DEFAULT_RESULT)}

    async def _runner() -> None:
        result = await plugin.execute_job(dict(job))
        if _is_str_object_dict(result):
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


def _validate_author_title_payload(author: str, title: str) -> dict[str, object]:
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
    author_result = _as_str_object_dict(author_payload) or dict(_DEFAULT_AUTHOR)
    book_result = _as_str_object_dict(book_payload) or dict(_DEFAULT_BOOK)
    return {
        "provider": str(result.get("provider") or "metadata_openlibrary"),
        "author": author_result,
        "book": book_result,
    }


class _ValidateAuthorTitleCallable:
    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], tuple[dict[str, object], dict[str, object]]] = {}

    def cache_clear(self) -> None:
        self._cache.clear()

    def __call__(
        self,
        author: str,
        title: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        cache_key = (author, title)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return dict(cached[0]), dict(cached[1])

        result = _validate_author_title_payload(author, title)
        author_result = _as_str_object_dict(result.get("author"))
        book_result = _as_str_object_dict(result.get("book"))
        self._cache[cache_key] = (dict(author_result), dict(book_result))
        return dict(author_result), dict(book_result)


validate_author_title = _ValidateAuthorTitleCallable()


__all__ = ["validate_author_title"]
