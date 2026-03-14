"""Renderer-facing ui.items projection for v3 prompt-select steps.

ASCII-only.
"""

from __future__ import annotations

from typing import Any


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _display_item(*, item_id: str, label: str) -> dict[str, str]:
    return {
        "display_label": label,
        "item_id": item_id,
        "label": label,
    }


def _author_label(
    *,
    author_id: str,
    author_to_books: dict[str, Any],
    book_meta: dict[str, Any],
) -> str:
    for book_id in _string_list(author_to_books.get(author_id)):
        meta = _mapping(book_meta.get(book_id))
        label = str(meta.get("author_label") or "").strip()
        if label:
            return label
    return author_id


def _book_label(*, book_id: str, book_meta: dict[str, Any]) -> str:
    meta = _mapping(book_meta.get(book_id))
    for key in ("display_label", "book_label", "label"):
        label = str(meta.get(key) or "").strip()
        if label:
            return label
    return book_id


def build_prompt_select_ui_items(*, step_id: str, state: dict[str, Any]) -> list[dict[str, str]]:
    vars_any = state.get("vars")
    vars_map = dict(vars_any) if isinstance(vars_any, dict) else {}
    phase1 = _mapping(vars_map.get("phase1"))
    if not phase1:
        return []

    book_meta = _mapping(phase1.get("book_meta"))

    if step_id == "select_authors":
        authors = _mapping(phase1.get("select_authors"))
        author_to_books = _mapping(phase1.get("author_to_books"))
        items: list[dict[str, str]] = []
        for author_id in _string_list(authors.get("ordered_ids")):
            items.append(
                _display_item(
                    item_id=author_id,
                    label=_author_label(
                        author_id=author_id,
                        author_to_books=author_to_books,
                        book_meta=book_meta,
                    ),
                )
            )
        return items

    if step_id == "select_books":
        books = _mapping(phase1.get("select_books"))
        ordered_ids = _string_list(books.get("filtered_ids"))
        if not ordered_ids:
            ordered_ids = _string_list(books.get("ordered_ids"))
        return [
            _display_item(item_id=book_id, label=_book_label(book_id=book_id, book_meta=book_meta))
            for book_id in ordered_ids
        ]

    return []


__all__ = ["build_prompt_select_ui_items"]
