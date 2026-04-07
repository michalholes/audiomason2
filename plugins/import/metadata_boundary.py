"""Import-owned metadata validation boundary adapter.

ASCII-only.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Coroutine
from functools import lru_cache
from typing import Any


def _callable_attr(obj: object, name: str) -> Any | None:
    value = getattr(obj, name, None)
    return value if callable(value) else None


def _builder_runner(
    plugin: object,
) -> Callable[[object], Coroutine[Any, Any, dict[str, Any]]] | None:
    for runner_name in ("_execute_job", "execute_request"):
        runner = _callable_attr(plugin, runner_name)
        if runner is not None:
            return runner
    return None


def _builder_attr(plugin: object, *names: str) -> Callable[..., object] | None:
    for name in names:
        builder = _callable_attr(plugin, name)
        if builder is not None:
            return builder
    return None


_DEFAULT_AUTHOR = {"valid": False, "canonical": None, "suggestion": None}
_DEFAULT_BOOK = {"valid": False, "canonical": None, "suggestion": None}


def _run_async(
    *,
    factory: Callable[[], Coroutine[Any, Any, dict[str, Any]]],
    default: dict[str, Any],
) -> dict[str, Any]:
    def _direct() -> dict[str, Any]:
        result: dict[str, Any] = asyncio.run(factory())
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
            result: dict[str, Any] = asyncio.run(factory())
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


@lru_cache(maxsize=128)
def validate_author_title(author: str, title: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if not author or not title:
        return dict(_DEFAULT_AUTHOR), dict(_DEFAULT_BOOK)
    try:
        from plugins.metadata_openlibrary.plugin import OpenLibraryPlugin
    except Exception:
        return dict(_DEFAULT_AUTHOR), dict(_DEFAULT_BOOK)

    plugin = OpenLibraryPlugin(
        {
            "timeout_seconds": 0.1,
            "max_response_bytes": OpenLibraryPlugin.DEFAULT_MAX_RESPONSE_BYTES,
        }
    )

    runner = _builder_runner(plugin)
    author_builder = _builder_attr(
        plugin,
        "build_validate_author_job",
        "build_validate_author_request",
    )
    book_builder = _builder_attr(
        plugin,
        "build_validate_book_job",
        "build_validate_book_request",
    )
    if runner is not None and author_builder is not None and book_builder is not None:
        author_validation = _run_async(
            factory=lambda: runner(author_builder(author)),
            default=_DEFAULT_AUTHOR,
        )
        validated_author = str(
            author_validation.get("canonical") or author_validation.get("suggestion") or author
        )
        book_validation = _run_async(
            factory=lambda: runner(book_builder(validated_author, title)),
            default=_DEFAULT_BOOK,
        )
        return dict(author_validation), dict(book_validation)

    validate_author = _callable_attr(plugin, "validate_author")
    validate_book = _callable_attr(plugin, "validate_book")
    if validate_author is None or validate_book is None:
        return dict(_DEFAULT_AUTHOR), dict(_DEFAULT_BOOK)

    author_validation = _run_async(
        factory=lambda: validate_author(author),
        default=_DEFAULT_AUTHOR,
    )
    validated_author = str(
        author_validation.get("canonical") or author_validation.get("suggestion") or author
    )
    book_validation = _run_async(
        factory=lambda: validate_book(validated_author, title),
        default=_DEFAULT_BOOK,
    )
    return dict(author_validation), dict(book_validation)


__all__ = ["validate_author_title"]
