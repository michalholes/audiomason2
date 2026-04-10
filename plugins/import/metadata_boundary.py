"""Import-owned metadata validation boundary adapter.

ASCII-only.
"""

from __future__ import annotations

import asyncio
import threading
from functools import lru_cache
from importlib import import_module
from pathlib import Path
from typing import Any

from audiomason.core.config_service import ConfigService
from audiomason.core.loader import PluginLoader
from audiomason.core.plugin_registry import PluginRegistry

_DEFAULT_AUTHOR = {"valid": False, "canonical": None, "suggestion": None}
_DEFAULT_BOOK = {"valid": False, "canonical": None, "suggestion": None}
_DEFAULT_RESULT = {
    "provider": "metadata_openlibrary",
    "author": dict(_DEFAULT_AUTHOR),
    "book": dict(_DEFAULT_BOOK),
}


def _builtin_plugins_root() -> Path:
    plugins_pkg = import_module("plugins")
    pkg_file = getattr(plugins_pkg, "__file__", None)
    if not isinstance(pkg_file, str) or not pkg_file:
        raise RuntimeError("plugins package path unavailable")
    return Path(pkg_file).resolve().parent


def _user_plugins_root() -> Path:
    return Path.home() / ".audiomason/plugins"


def _metadata_plugin_loader() -> PluginLoader:
    return PluginLoader(
        builtin_plugins_dir=_builtin_plugins_root(),
        user_plugins_dir=_user_plugins_root(),
        registry=PluginRegistry(ConfigService()),
    )


def _apply_phase1_metadata_config(*, plugin: Any) -> None:
    default_max_bytes = getattr(plugin, "DEFAULT_MAX_RESPONSE_BYTES", 2 * 1024 * 1024)
    plugin.config = {
        "timeout_seconds": 0.1,
        "max_response_bytes": default_max_bytes,
    }
    try:
        plugin.timeout_seconds = float(plugin.config["timeout_seconds"])
    except (TypeError, ValueError):
        plugin.timeout_seconds = 0.1
    try:
        plugin.max_response_bytes = int(plugin.config["max_response_bytes"])
    except (TypeError, ValueError):
        plugin.max_response_bytes = int(default_max_bytes)


def _resolve_metadata_plugin() -> Any:
    loader = _metadata_plugin_loader()
    for plugin_dir in loader.discover():
        manifest = loader.load_manifest_only(plugin_dir)
        if manifest.name != "metadata_openlibrary":
            continue
        plugin = loader.load_plugin(plugin_dir, validate=False)
        _apply_phase1_metadata_config(plugin=plugin)
        return plugin
    raise RuntimeError("required_metadata_plugin_not_found:metadata_openlibrary")


def _build_phase1_validation_job(*, plugin: Any, author: str, title: str) -> dict[str, Any] | None:
    builder = getattr(plugin, "build_phase1_validation_job", None)
    if not callable(builder):
        return None
    built = builder(author, title)
    return dict(built) if isinstance(built, dict) else None


def _run_async(*, factory: Any, default: dict[str, Any]) -> dict[str, Any]:
    def _direct() -> dict[str, Any]:
        result = asyncio.run(factory())
        return dict(result) if isinstance(result, dict) else dict(default)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            return _direct()
        except Exception:
            return dict(default)

    result_box: dict[str, Any] = dict(default)
    error_box: list[BaseException] = []

    def _runner() -> None:
        try:
            result = asyncio.run(factory())
            if isinstance(result, dict):
                result_box.clear()
                result_box.update(dict(result))
        except Exception as exc:
            error_box.append(exc)

    worker = threading.Thread(target=_runner, daemon=True)
    worker.start()
    worker.join()
    if error_box:
        return dict(default)
    return dict(result_box)


async def _run_phase1_validation_job_boundary(
    *,
    job: dict[str, Any],
    plugin: Any,
) -> dict[str, Any]:
    runner = getattr(plugin, "_execute_job", None)
    if not callable(runner):
        raise RuntimeError("metadata_phase1_job_runner_missing")
    result = await runner(dict(job))
    return dict(result) if isinstance(result, dict) else dict(_DEFAULT_RESULT)


def _validate_author_title_payload(author: str, title: str) -> dict[str, Any]:
    if not author or not title:
        return dict(_DEFAULT_RESULT)
    try:
        plugin = _resolve_metadata_plugin()
        job = _build_phase1_validation_job(plugin=plugin, author=author, title=title)
        if job is None:
            return dict(_DEFAULT_RESULT)
        result = _run_async(
            factory=lambda: _run_phase1_validation_job_boundary(job=job, plugin=plugin),
            default=_DEFAULT_RESULT,
        )
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
