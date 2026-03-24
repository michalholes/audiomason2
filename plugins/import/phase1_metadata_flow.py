"""Deterministic metadata projection for PHASE 1 import sessions.

ASCII-only.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Coroutine
from copy import deepcopy
from functools import lru_cache
from typing import Any

DEFAULT_FILENAME_POLICY = {"mode": "keep", "template": "{author}/{title}"}
DEFAULT_FIELD_MAP = {
    "title": "title",
    "artist": "artist",
    "album": "album",
    "album_artist": "album_artist",
}
_ROOT_AUDIO_AUTHOR = "__ROOT_AUDIO__"
_ROOT_AUDIO_TITLE = "Untitled"
_ROOT_SENTINELS = {"", "(root)"}


def _answer_dict(state: dict[str, Any], key: str) -> dict[str, Any]:
    answers_any = state.get("answers")
    answers = dict(answers_any) if isinstance(answers_any, dict) else {}
    value = answers.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _normalize_root_audio_value(*, value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if text in _ROOT_SENTINELS:
        return fallback
    return text or fallback


def _run_async_validation(
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
def _openlibrary_validate(author: str, title: str) -> tuple[dict[str, Any], dict[str, Any]]:
    default_author = {"valid": False, "canonical": None, "suggestion": None}
    default_book = {"valid": False, "canonical": None, "suggestion": None}
    if not author or not title:
        return default_author, default_book
    try:
        from plugins.metadata_openlibrary.plugin import OpenLibraryPlugin
    except Exception:
        return default_author, default_book

    plugin = OpenLibraryPlugin(
        {
            "timeout_seconds": 0.1,
            "max_response_bytes": OpenLibraryPlugin.DEFAULT_MAX_RESPONSE_BYTES,
        }
    )

    author_validation = _run_async_validation(
        factory=lambda: plugin.validate_author(author),
        default=default_author,
    )

    validated_author = str(
        author_validation.get("canonical") or author_validation.get("suggestion") or author
    )

    book_validation = _run_async_validation(
        factory=lambda: plugin.validate_book(validated_author, title),
        default=default_book,
    )

    return dict(author_validation), dict(book_validation)


def _validated_author_title(*, author: str, title: str) -> tuple[dict[str, Any], str, str]:
    author_validation, book_validation = _openlibrary_validate(author, title)

    canonical_author = str(author_validation.get("canonical") or author)
    suggestion_author = author_validation.get("suggestion")
    if isinstance(suggestion_author, str) and suggestion_author.strip():
        canonical_author = suggestion_author.strip()

    canonical_title = title
    canonical_book = book_validation.get("canonical")
    suggestion_book = book_validation.get("suggestion")
    if isinstance(canonical_book, dict):
        canonical_author = str(canonical_book.get("author") or canonical_author)
        canonical_title = str(canonical_book.get("title") or canonical_title)
    elif isinstance(suggestion_book, dict):
        canonical_author = str(suggestion_book.get("author") or canonical_author)
        canonical_title = str(suggestion_book.get("title") or canonical_title)

    canonical_author = _normalize_root_audio_value(
        value=canonical_author,
        fallback=_ROOT_AUDIO_AUTHOR,
    )
    canonical_title = _normalize_root_audio_value(
        value=canonical_title,
        fallback=_ROOT_AUDIO_TITLE,
    )

    return (
        {
            "provider": "metadata_openlibrary",
            "author": dict(author_validation),
            "book": dict(book_validation),
        },
        canonical_author,
        canonical_title,
    )


def build_phase1_metadata_projection(
    *,
    source_projection: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    book_meta_any = source_projection.get("book_meta")
    source_book_meta = dict(book_meta_any) if isinstance(book_meta_any, dict) else {}
    selected_any = source_projection.get("select_books")
    selected = dict(selected_any) if isinstance(selected_any, dict) else {}
    selected_ids_any = selected.get("selected_ids")
    selected_ids = (
        [item for item in selected_ids_any if isinstance(item, str)]
        if isinstance(selected_ids_any, list)
        else []
    )
    selected_paths_any = selected.get("selected_source_relative_paths")
    selected_paths = (
        [item for item in selected_paths_any if isinstance(item, str)]
        if isinstance(selected_paths_any, list)
        else []
    )

    validated_books: dict[str, dict[str, Any]] = {}
    for book_id in selected_ids:
        source_book = source_book_meta.get(book_id, {})
        source_author = _normalize_root_audio_value(
            value=source_book.get("author_label"),
            fallback=_ROOT_AUDIO_AUTHOR,
        )
        source_title = _normalize_root_audio_value(
            value=source_book.get("book_label"),
            fallback=_ROOT_AUDIO_TITLE,
        )
        validation, validated_author, validated_title = _validated_author_title(
            author=source_author,
            title=source_title,
        )
        validated_books[book_id] = {
            "source_author": source_author,
            "source_title": source_title,
            "author_label": validated_author,
            "book_label": validated_title,
            "display_label": (
                validated_author
                if validated_author == validated_title
                else f"{validated_author} / {validated_title}"
            ),
            "source_relative_path": str(source_book.get("source_relative_path") or ""),
            "validation": validation,
        }

    first_book = validated_books.get(selected_ids[0], {}) if selected_ids else {}
    source_author = str(first_book.get("source_author") or _ROOT_AUDIO_AUTHOR)
    source_title = str(first_book.get("source_title") or _ROOT_AUDIO_TITLE)

    author_answer = _answer_dict(state, "effective_author")
    title_answer = _answer_dict(state, "effective_title")
    merged_answer = _answer_dict(state, "effective_author_title")

    author_override_raw = author_answer.get("author")
    if author_override_raw is None:
        author_override_raw = merged_answer.get("author")
    title_override_raw = title_answer.get("title")
    if title_override_raw is None:
        title_override_raw = merged_answer.get("title")

    author_override_present = author_override_raw is not None
    title_override_present = title_override_raw is not None

    if author_override_present or title_override_present:
        for book_id in selected_ids:
            current = dict(validated_books.get(book_id) or {})
            requested_author_source = (
                author_override_raw if author_override_present else current.get("author_label")
            )
            requested_author = _normalize_root_audio_value(
                value=requested_author_source,
                fallback=str(current.get("author_label") or _ROOT_AUDIO_AUTHOR),
            )
            requested_title = _normalize_root_audio_value(
                value=(title_override_raw if title_override_present else current.get("book_label")),
                fallback=str(current.get("book_label") or _ROOT_AUDIO_TITLE),
            )
            validation, canonical_author, canonical_title = _validated_author_title(
                author=requested_author,
                title=requested_title,
            )
            validated_books[book_id] = {
                **current,
                "author_label": canonical_author,
                "book_label": canonical_title,
                "display_label": (
                    canonical_author
                    if canonical_author == canonical_title
                    else f"{canonical_author} / {canonical_title}"
                ),
                "validation": validation,
            }

    effective_book = validated_books.get(selected_ids[0], {}) if selected_ids else {}
    normalized_author = _normalize_root_audio_value(
        value=effective_book.get("author_label"),
        fallback=_ROOT_AUDIO_AUTHOR,
    )
    normalized_book_title = _normalize_root_audio_value(
        value=effective_book.get("book_label"),
        fallback=_ROOT_AUDIO_TITLE,
    )
    effective_author_title = {
        "author": normalized_author,
        "title": normalized_book_title,
    }
    validation = dict(effective_book.get("validation") or {})

    filename_policy = deepcopy(DEFAULT_FILENAME_POLICY)
    filename_policy.update(
        {
            "author": normalized_author,
            "title": normalized_book_title,
        }
    )
    filename_policy.update(_answer_dict(state, "filename_policy"))

    default_values = {
        "title": normalized_book_title,
        "artist": normalized_author,
        "album": normalized_book_title,
        "album_artist": normalized_author,
    }
    id3_policy = {
        "field_map": deepcopy(DEFAULT_FIELD_MAP),
        "values": default_values,
    }
    id3_policy.update(_answer_dict(state, "id3_policy"))
    field_map = dict(id3_policy.get("field_map") or {})
    values = dict(id3_policy.get("values") or {})

    return {
        "source_author": source_author,
        "book_title": source_title,
        "normalize_author": normalized_author,
        "normalize_book_title": normalized_book_title,
        "validation": validation,
        "effective_author_title": effective_author_title,
        "filename_policy": filename_policy,
        "field_map": field_map,
        "values": values,
        "selected_book_ids": selected_ids,
        "selected_source_relative_paths": selected_paths,
        "authority_by_book": validated_books,
    }
