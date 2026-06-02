"""Import-owned metadata validation boundary adapter.

ASCII-only.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Protocol, TypeGuard, cast

from audiomason.core.config_service import ConfigService
from audiomason.core.errors import PluginNotFoundError
from audiomason.core.loader import PluginLoader
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
_DEFAULT_AI_RESULT = {
    "provider": "metadata_ai",
    "author": dict(_DEFAULT_AUTHOR),
    "book": dict(_DEFAULT_BOOK),
}
_PHASE1_METADATA_TIMEOUT_SECONDS = 2.0
_PERSISTENT_CACHE_PATH = Path.home() / ".cache" / "audiomason" / "metadata_validation_cache.json"


class _Phase1ValidationJobBuilder(Protocol):
    def __call__(self, author: str, title: str) -> dict[str, object]: ...


class _MetadataPhase1ValidationPlugin(Protocol):
    DEFAULT_MAX_RESPONSE_BYTES: int
    config: dict[str, object]
    timeout_seconds: float
    max_response_bytes: int

    async def execute_job(self, job: dict[str, object]) -> dict[str, object]: ...


class _AITitleValidationJobBuilder(Protocol):
    def __call__(self, author: str, title: str) -> dict[str, object]: ...


class _MetadataAITitleValidationPlugin(Protocol):
    config: dict[str, object]
    enabled: bool
    endpoint: str
    provider: str
    model: str
    api_key: str
    timeout_seconds: float
    max_response_bytes: int

    async def execute_job(self, job: dict[str, object]) -> dict[str, object]: ...


class _JobExecutorPlugin(Protocol):
    async def execute_job(self, job: dict[str, object]) -> dict[str, object]: ...


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


def _to_bool_or_default(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        norm = value.strip().lower()
        if norm in {"1", "true", "yes", "on"}:
            return True
        if norm in {"0", "false", "no", "off"}:
            return False
    return default


def _normalize_cache_text(value: str) -> str:
    return " ".join(str(value).split()).casefold()


def _validation_cache_key(author: str, title: str) -> tuple[str, str]:
    return (_normalize_cache_text(author), _normalize_cache_text(title))


def _builtin_plugins_dir() -> Path:
    return Path(__file__).resolve().parents[1]


_callable_authority_cache: tuple[PluginRegistry, PluginLoader] | None = None


def _callable_authority() -> tuple[PluginRegistry, PluginLoader]:
    global _callable_authority_cache
    if _callable_authority_cache is None:
        registry = PluginRegistry(ConfigService())
        loader = PluginLoader(
            builtin_plugins_dir=_builtin_plugins_dir(),
            registry=registry,
        )
        _callable_authority_cache = (registry, loader)
    return _callable_authority_cache


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


def _plugin_config(plugin_id: str) -> dict[str, object]:
    registry, _loader = _callable_authority()
    return registry.get_plugin_config(plugin_id)


def _tune_metadata_ai_plugin(
    plugin: _MetadataAITitleValidationPlugin,
) -> _MetadataAITitleValidationPlugin:
    config = _as_str_object_dict(_plugin_config("metadata_ai"))
    plugin.config = config
    plugin.enabled = _to_bool_or_default(config.get("enabled"), False)
    plugin.endpoint = str(config.get("endpoint") or "").strip()
    plugin.provider = str(config.get("provider") or "").strip()
    plugin.model = str(config.get("model") or "").strip()
    plugin.api_key = str(config.get("api_key") or "").strip()
    plugin.timeout_seconds = _to_float_or_default(config.get("timeout_seconds"), 2.0)
    plugin.max_response_bytes = _to_int_or_default(config.get("max_response_bytes"), 256 * 1024)
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


def _resolve_ai_title_validation_authority() -> tuple[
    _AITitleValidationJobBuilder,
    _MetadataAITitleValidationPlugin,
]:
    registry, loader = _callable_authority()
    published = registry.resolve_wizard_callable(
        "metadata.ai_title_validate",
        loader=loader,
    )
    if published.execution_mode != "job":
        raise RuntimeError(
            "wizard_callable_execution_mode_mismatch:"
            f"metadata.ai_title_validate:{published.execution_mode}"
        )
    try:
        plugin_any = loader.get_plugin(published.plugin_id)
    except PluginNotFoundError:
        plugin_any = loader.load_plugin(published.manifest_path.parent, validate=False)
    plugin = _tune_metadata_ai_plugin(cast(_MetadataAITitleValidationPlugin, plugin_any))
    callable_def = RegisteredWizardCallable(
        plugin_id=published.plugin_id,
        plugin_dir=published.manifest_path.parent,
        manifest_path=published.manifest_path,
        operation_id=published.operation_id,
        method_name=published.method_name,
        execution_mode=published.execution_mode,
    )
    build_job = cast(
        _AITitleValidationJobBuilder,
        resolve_registered_wizard_callable(
            plugin_obj=plugin,
            callable_def=callable_def,
        ),
    )
    return build_job, plugin


def _run_phase1_validation_job(
    *,
    job: dict[str, object],
    plugin: _JobExecutorPlugin,
) -> dict[str, object]:
    result_box: dict[str, dict[str, object]] = {"result": dict(_DEFAULT_RESULT)}

    async def _runner() -> None:
        result = await plugin.execute_job(dict(job))
        if _is_str_object_dict(result):
            result_box["result"] = dict(result)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        for attempt in range(2):
            try:
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(_runner())
                    loop.run_until_complete(loop.shutdown_asyncgens())
                finally:
                    asyncio.set_event_loop(None)
                    loop.close()
            except Exception as exc:
                if attempt >= 1:
                    return dict(_DEFAULT_RESULT)
                message = str(exc).lower()
                if not any(
                    token in message for token in ("timeout", "timed out", "handshake", "http 429")
                ):
                    return dict(_DEFAULT_RESULT)
                time.sleep(0.25)
                continue
            return dict(result_box["result"])
        return dict(_DEFAULT_RESULT)
    return dict(_DEFAULT_RESULT)


def _merge_ai_author_title_result(
    *,
    author: str,
    title: str,
    primary: dict[str, object],
    ai: dict[str, object],
) -> dict[str, object]:
    provider = str(primary.get("provider") or "metadata_openlibrary")
    author_result = _as_str_object_dict(primary.get("author")) or dict(_DEFAULT_AUTHOR)
    book_result = _as_str_object_dict(primary.get("book")) or dict(_DEFAULT_BOOK)

    if bool(author_result.get("valid")) and bool(book_result.get("valid")):
        return {
            "provider": provider,
            "author": author_result,
            "book": book_result,
        }

    ai_author_payload = _as_str_object_dict(ai.get("author"))
    ai_author = str(ai_author_payload.get("suggestion") or "").strip()
    ai_book = _as_str_object_dict(ai.get("book"))
    ai_suggestion_any = ai_book.get("suggestion")
    ai_suggestion = _as_str_object_dict(ai_suggestion_any)
    if not ai_author:
        ai_author = str(ai_suggestion.get("author") or "").strip()
    ai_title = str(ai_suggestion.get("title") or "").strip()
    if not ai_author and not ai_title:
        return {
            "provider": provider,
            "author": author_result,
            "book": book_result,
        }

    current_author_suggestion = str(author_result.get("suggestion") or "").strip()
    if ai_author and not bool(author_result.get("valid")):
        author_result["suggestion"] = ai_author
        current_author_suggestion = ai_author

    suggestion_any = book_result.get("suggestion")
    suggestion = _as_str_object_dict(suggestion_any)
    current_author = str(suggestion.get("author") or current_author_suggestion or author).strip()
    if not current_author:
        current_author = author
    if ai_author:
        current_author = ai_author
    current_title = str(suggestion.get("title") or title).strip()
    if not current_title:
        current_title = title
    if ai_title:
        current_title = ai_title

    book_result["suggestion"] = {
        "author": current_author,
        "title": current_title,
    }
    return {
        "provider": provider,
        "author": author_result,
        "book": book_result,
    }


def _has_validation_signal(
    *,
    author_result: dict[str, object],
    book_result: dict[str, object],
) -> bool:
    if bool(author_result.get("valid")) or bool(book_result.get("valid")):
        return True

    author_suggestion = str(author_result.get("suggestion") or "").strip()
    author_canonical = str(author_result.get("canonical") or "").strip()
    if author_suggestion or author_canonical:
        return True

    for key in ("canonical", "suggestion"):
        candidate = book_result.get(key)
        if _is_str_object_dict(candidate):
            book_author = str(candidate.get("author") or "").strip()
            book_title = str(candidate.get("title") or "").strip()
            if book_author or book_title:
                return True
    return False


def _load_persistent_validation_cache() -> dict[
    tuple[str, str], tuple[dict[str, object], dict[str, object]]
]:
    if not _PERSISTENT_CACHE_PATH.exists():
        return {}
    try:
        raw = _PERSISTENT_CACHE_PATH.read_text(encoding="utf-8")
        loaded_any: object = json.loads(raw)
    except Exception:
        return {}
    if not _is_str_object_dict(loaded_any):
        return {}
    data = loaded_any
    out: dict[tuple[str, str], tuple[dict[str, object], dict[str, object]]] = {}
    for key, value in data.items():
        if "\n" not in key:
            continue
        if not _is_str_object_dict(value):
            continue
        author, title = key.split("\n", 1)
        author_result = _as_str_object_dict(value.get("author"))
        book_result = _as_str_object_dict(value.get("book"))
        if not _has_validation_signal(author_result=author_result, book_result=book_result):
            continue
        out[(author, title)] = (dict(author_result), dict(book_result))
    return out


def _save_persistent_validation_cache(
    cache: dict[tuple[str, str], tuple[dict[str, object], dict[str, object]]],
) -> None:
    serializable: dict[str, dict[str, object]] = {}
    for (author, title), (author_result, book_result) in cache.items():
        if not _has_validation_signal(author_result=author_result, book_result=book_result):
            continue
        key = f"{author}\n{title}"
        serializable[key] = {
            "author": dict(author_result),
            "book": dict(book_result),
        }
    try:
        _PERSISTENT_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PERSISTENT_CACHE_PATH.write_text(
            json.dumps(serializable, ensure_ascii=True, sort_keys=True),
            encoding="utf-8",
        )
    except Exception:
        return


def _validate_author_title_payload(author: str, title: str) -> dict[str, object]:
    if not author or not title:
        return dict(_DEFAULT_RESULT)
    primary_result: dict[str, object]
    try:
        build_job, plugin = _resolve_phase1_validation_authority()
        job = build_job(author, title)
        primary_result = _run_phase1_validation_job(job=dict(job), plugin=plugin)
    except Exception:
        primary_result = dict(_DEFAULT_RESULT)

    ai_result: dict[str, object] = dict(_DEFAULT_AI_RESULT)
    try:
        build_ai_job, ai_plugin = _resolve_ai_title_validation_authority()
        ai_job = build_ai_job(author, title)
        ai_result = _run_phase1_validation_job(job=dict(ai_job), plugin=ai_plugin)
    except Exception:
        ai_result = dict(_DEFAULT_AI_RESULT)

    return _merge_ai_author_title_result(
        author=author,
        title=title,
        primary=primary_result,
        ai=ai_result,
    )


class _ValidateAuthorTitleCallable:
    def __init__(self) -> None:
        self._cache = _load_persistent_validation_cache()

    def cache_clear(self) -> None:
        self._cache.clear()
        _save_persistent_validation_cache(self._cache)

    def __call__(
        self,
        author: str,
        title: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        cache_key = _validation_cache_key(author, title)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return dict(cached[0]), dict(cached[1])

        result = _validate_author_title_payload(author, title)
        author_result = _as_str_object_dict(result.get("author"))
        book_result = _as_str_object_dict(result.get("book"))
        if _has_validation_signal(author_result=author_result, book_result=book_result):
            self._cache[cache_key] = (dict(author_result), dict(book_result))
            _save_persistent_validation_cache(self._cache)
            return dict(author_result), dict(book_result)

        cached = self._cache.get(cache_key)
        if cached is not None:
            return dict(cached[0]), dict(cached[1])
        return dict(author_result), dict(book_result)


validate_author_title = _ValidateAuthorTitleCallable()


__all__ = ["validate_author_title"]
