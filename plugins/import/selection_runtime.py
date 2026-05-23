"""Runtime selection items utilities for Import Wizard.

This module exists to keep plugins/import/engine.py from growing beyond
monolith gate thresholds.

ASCII-only.
"""

from __future__ import annotations

from typing import TypeGuard, cast

from .fingerprints import sha256_hex


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _item_sort_key(item: dict[str, str]) -> tuple[str, str]:
    return (item.get("label", ""), item.get("item_id", ""))


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _to_ascii(text: str) -> str:
    # Deterministic ASCII-only conversion for UI labels.
    return text.encode("ascii", errors="replace").decode("ascii")


def derive_selection_items(
    discovery: list[dict[str, object]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Derive stable author/book selectable items from discovery.

    Item ids and ordering must be deterministic.
    """

    authors: dict[str, dict[str, str]] = {}
    books: dict[str, dict[str, str]] = {}

    dirs: list[str] = []
    for it in discovery:
        if not (_is_str_object_dict(it) and it.get("kind") == "dir"):
            continue
        rel_any = it.get("relative_path")
        if not isinstance(rel_any, str):
            continue
        dirs.append(rel_any.replace("\\", "/"))

    # Prefer book directories at depth >= 2 (Author/Book). If absent, fall back
    # to depth >= 1 (single folder sources).
    book_pairs: set[tuple[str, str]] = set()
    for rel in dirs:
        segs = [s for s in rel.split("/") if s]
        if len(segs) >= 2:
            book_pairs.add((segs[0], segs[1]))

    if not book_pairs:
        for rel in dirs:
            segs = [s for s in rel.split("/") if s]
            if len(segs) >= 1:
                book_pairs.add((segs[0], segs[0]))

    if not book_pairs:
        book_pairs.add(("(root)", "(root)"))

    for author_key, book_key in sorted(book_pairs):
        author_label = _to_ascii(author_key)
        author_display_label = author_key
        book_label = _to_ascii(
            author_key if author_key == book_key else f"{author_key} / {book_key}"
        )

        book_display_label = author_key if author_key == book_key else f"{author_key} / {book_key}"
        author_id = "author:" + sha256_hex(f"a|{author_key}".encode())[:16]
        book_id = "book:" + sha256_hex(f"b|{author_key}|{book_key}".encode())[:16]

        if author_id not in authors:
            authors[author_id] = {
                "item_id": author_id,
                "label": author_label,
                "display_label": author_display_label,
            }
        if book_id not in books:
            books[book_id] = {
                "item_id": book_id,
                "label": book_label,
                "display_label": book_display_label,
            }

    authors_items = sorted(list(authors.values()), key=_item_sort_key)
    books_items = sorted(list(books.values()), key=_item_sort_key)
    return authors_items, books_items


def inject_selection_items(
    *,
    effective_model: dict[str, object],
    authors_items: list[dict[str, str]],
    books_items: list[dict[str, str]],
) -> dict[str, object]:
    steps_any = effective_model.get("steps")
    if not _is_object_list(steps_any):
        return effective_model

    steps: list[dict[str, object]] = [dict(step) for step in steps_any if _is_str_object_dict(step)]
    for step in steps:
        step_id = step.get("step_id")
        if step_id not in {"select_authors", "select_books"}:
            continue
        fields_any = step.get("fields")
        if not _is_object_list(fields_any):
            continue
        fields: list[dict[str, object]] = [
            dict(field) for field in fields_any if _is_str_object_dict(field)
        ]
        for f in fields:
            if f.get("type") != "multi_select_indexed":
                continue
            if step_id == "select_authors":
                f["items"] = list(authors_items)
            else:
                f["items"] = list(books_items)

    effective_model["steps"] = steps
    return effective_model
