"""Renderer-facing ui.items projection for v3 prompt-select steps.

ASCII-only.
"""

from __future__ import annotations

from typing import TypeGuard, cast


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _string_list(value: object) -> list[str]:
    if not _is_object_list(value):
        return []
    return [item for item in value if isinstance(item, str)]


def _display_item(*, item_id: str, label: str) -> dict[str, str]:
    return {
        "display_label": label,
        "item_id": item_id,
        "label": label,
    }


def _author_rows(phase1: dict[str, object]) -> list[dict[str, object]]:
    authors_any = phase1.get("authors")
    if not _is_object_list(authors_any):
        return []
    return [_mapping(item) for item in authors_any if _is_str_object_dict(item)]


def _book_rows(phase1: dict[str, object]) -> list[dict[str, object]]:
    books_any = phase1.get("books")
    if not _is_object_list(books_any):
        return []
    return [_mapping(item) for item in books_any if _is_str_object_dict(item)]


def _book_label(book: dict[str, object]) -> str:
    for key in ("display_label", "book_label", "label"):
        label = str(book.get(key) or "").strip()
        if label:
            return label
    return str(book.get("book_id") or "")


def build_prompt_select_ui_items(*, step_id: str, state: dict[str, object]) -> list[dict[str, str]]:
    vars_any = state.get("vars")
    vars_map = _mapping(vars_any)
    phase1 = _mapping(vars_map.get("phase1"))
    if not phase1:
        return []

    if step_id == "select_authors":
        return [
            _display_item(
                item_id=str(author.get("author_id") or ""),
                label=str(author.get("author_label") or author.get("author_id") or ""),
            )
            for author in _author_rows(phase1)
            if str(author.get("author_id") or "")
        ]

    if step_id == "select_books":
        books = _mapping(phase1.get("select_books"))
        ordered_ids = _string_list(books.get("filtered_ids"))
        books_by_id = {
            str(book.get("book_id") or ""): book
            for book in _book_rows(phase1)
            if str(book.get("book_id") or "")
        }
        items: list[dict[str, str]] = []
        for book_id in ordered_ids:
            book = books_by_id.get(book_id)
            if book is None:
                continue
            items.append(_display_item(item_id=book_id, label=_book_label(book)))
        return items

    return []


__all__ = ["build_prompt_select_ui_items"]
