"""Deterministic metadata projection for PHASE 1 import sessions.

ASCII-only.
"""

from __future__ import annotations

import asyncio
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

    try:
        author_validation = asyncio.run(plugin.validate_author(author))
    except Exception:
        author_validation = default_author

    validated_author = str(
        author_validation.get("canonical") or author_validation.get("suggestion") or author
    )

    try:
        book_validation = asyncio.run(plugin.validate_book(validated_author, title))
    except Exception:
        book_validation = default_book

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
    book_meta = dict(book_meta_any) if isinstance(book_meta_any, dict) else {}
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

    first_book = book_meta.get(selected_ids[0], {}) if selected_ids else {}
    source_author = _normalize_root_audio_value(
        value=first_book.get("author_label"),
        fallback=_ROOT_AUDIO_AUTHOR,
    )
    source_title = _normalize_root_audio_value(
        value=first_book.get("book_label"),
        fallback=_ROOT_AUDIO_TITLE,
    )

    validation, validated_author, validated_title = _validated_author_title(
        author=source_author,
        title=source_title,
    )

    effective_author_title = {
        "author": validated_author,
        "title": validated_title,
    }
    effective_author_title.update(_answer_dict(state, "effective_author_title"))
    normalized_author = _normalize_root_audio_value(
        value=effective_author_title.get("author"),
        fallback=validated_author,
    )
    normalized_book_title = _normalize_root_audio_value(
        value=effective_author_title.get("title"),
        fallback=validated_title,
    )
    effective_author_title = {
        "author": normalized_author,
        "title": normalized_book_title,
    }

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
        "validation": validation,
        "effective_author_title": effective_author_title,
        "filename_policy": filename_policy,
        "field_map": field_map,
        "values": values,
        "normalize_author": normalized_author,
        "normalize_book_title": normalized_book_title,
        "selected_book_ids": selected_ids,
        "selected_source_relative_paths": selected_paths,
    }
