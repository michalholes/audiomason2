"""Deterministic metadata projection for PHASE 1 import sessions.

ASCII-only.
"""

from __future__ import annotations

from typing import Any


def build_phase1_metadata_projection(*, source_projection: dict[str, Any]) -> dict[str, Any]:
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

    first_book = book_meta.get(selected_ids[0], {}) if selected_ids else {}
    author_name = str(first_book.get("author_label") or "")
    book_title = str(first_book.get("book_label") or "")

    values = {
        "title": book_title,
        "artist": author_name,
        "album": book_title,
        "album_artist": author_name,
    }
    values = {key: value for key, value in values.items() if value}
    return {
        "author": author_name,
        "book": book_title,
        "normalize_author": author_name,
        "normalize_book_title": book_title,
        "field_map": {
            "title": "book_title",
            "artist": "author",
            "album": "book_title",
            "album_artist": "author",
        },
        "values": values,
    }
