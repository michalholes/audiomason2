"""Import-owned metadata validation boundary adapter.

ASCII-only.
"""

from __future__ import annotations

import asyncio
import threading
from functools import lru_cache
from typing import Any

from .engine_diagnostics_required import resolve_import_plugin

_DEFAULT_AUTHOR = {"valid": False, "canonical": None, "suggestion": None}
_DEFAULT_BOOK = {"valid": False, "canonical": None, "suggestion": None}
_DEFAULT_RESULT = {
    "provider": "metadata_openlibrary",
    "author": dict(_DEFAULT_AUTHOR),
    "book": dict(_DEFAULT_BOOK),
}


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
    runner = getattr(plugin, "execute_job", None)
    if not callable(runner):
        raise RuntimeError("metadata_phase1_job_runner_missing")
    result = await runner(dict(job))
    return dict(result) if isinstance(result, dict) else dict(_DEFAULT_RESULT)


def _validate_author_title_payload(author: str, title: str) -> dict[str, Any]:
    if not author or not title:
        return dict(_DEFAULT_RESULT)
    try:
        plugin = resolve_import_plugin(plugin_name="metadata_openlibrary")
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
