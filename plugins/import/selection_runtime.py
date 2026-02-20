"""Runtime selection items utilities for Import Wizard.

This module exists to keep plugins/import/engine.py from growing beyond
monolith gate thresholds.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from .fingerprints import sha256_hex


def _to_ascii(text: str) -> str:
    # Deterministic ASCII-only conversion for UI labels.
    return text.encode("ascii", errors="replace").decode("ascii")


def derive_selection_items(
    discovery: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Derive stable author/book selectable items from discovery.

    Item ids and ordering must be deterministic.
    """

    authors: dict[str, dict[str, str]] = {}
    books: dict[str, dict[str, str]] = {}

    dirs: list[str] = []
    for it in discovery:
        if not (isinstance(it, dict) and it.get("kind") == "dir"):
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
        book_label = _to_ascii(
            author_key if author_key == book_key else f"{author_key} / {book_key}"
        )

        author_id = "author:" + sha256_hex(f"a|{author_key}".encode())[:16]
        book_id = "book:" + sha256_hex(f"b|{author_key}|{book_key}".encode())[:16]

        if author_id not in authors:
            authors[author_id] = {"item_id": author_id, "label": author_label}
        if book_id not in books:
            books[book_id] = {"item_id": book_id, "label": book_label}

    authors_items = sorted(authors.values(), key=lambda x: (x["label"], x["item_id"]))
    books_items = sorted(books.values(), key=lambda x: (x["label"], x["item_id"]))
    return authors_items, books_items


def inject_selection_items(
    *,
    effective_model: dict[str, Any],
    authors_items: list[dict[str, str]],
    books_items: list[dict[str, str]],
) -> dict[str, Any]:
    steps_any = effective_model.get("steps")
    if not isinstance(steps_any, list):
        return effective_model

    steps: list[dict[str, Any]] = [s for s in steps_any if isinstance(s, dict)]
    for step in steps:
        step_id = step.get("step_id")
        if step_id not in {"select_authors", "select_books"}:
            continue
        fields_any = step.get("fields")
        if not isinstance(fields_any, list):
            continue
        fields: list[dict[str, Any]] = [f for f in fields_any if isinstance(f, dict)]
        for f in fields:
            if f.get("type") != "multi_select_indexed":
                continue
            if step_id == "select_authors":
                f["items"] = list(authors_items)
            else:
                f["items"] = list(books_items)

    effective_model["steps"] = steps
    return effective_model
