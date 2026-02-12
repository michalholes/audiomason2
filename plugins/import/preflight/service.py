"""Preflight (PHASE 0) service for import wizard.

Deterministic and read-only.
All filesystem operations go through file_io capability.

ASCII-only.
"""

from __future__ import annotations

import hashlib
from typing import Any

from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import RootName

from .types import BookFingerprint, BookPreflight, PreflightResult

_AUDIO_EXT = {".mp3", ".m4a", ".m4b", ".flac", ".wav", ".ogg", ".opus"}
_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def _emit_diag(event: str, *, operation: str, data: dict[str, Any]) -> None:
    try:
        env = build_envelope(
            event=event,
            component="import.preflight",
            operation=operation,
            data=data,
        )
        get_event_bus().publish(event, env)
    except Exception:
        return


class PreflightService:
    """Read-only preflight detection under a source root."""

    def __init__(self, fs: FileService) -> None:
        self._fs = fs

    def run(self, root: RootName, source_root_rel_path: str) -> PreflightResult:
        _emit_diag(
            "boundary.start",
            operation="run",
            data={"root": str(root), "source_root_rel_path": source_root_rel_path},
        )

        authors = self._list_authors(root, source_root_rel_path)
        books: list[BookPreflight] = []
        for author in authors:
            author_rel = _join(source_root_rel_path, author)
            for book in self._list_books(root, author_rel):
                book_rel = _join(author_rel, book)
                books.append(self._preflight_book(root, author, book, book_rel))

        books.sort(key=lambda b: (b.author, b.book, b.rel_path))

        res = PreflightResult(
            source_root_rel_path=source_root_rel_path,
            authors=authors,
            books=books,
        )
        _emit_diag(
            "boundary.end",
            operation="run",
            data={
                "root": str(root),
                "source_root_rel_path": source_root_rel_path,
                "status": "succeeded",
            },
        )
        return res

    def _list_authors(self, root: RootName, source_root_rel_path: str) -> list[str]:
        entries = self._fs.list_dir(root, source_root_rel_path, recursive=False)
        authors = sorted([_basename(e.rel_path) for e in entries if e.is_dir])
        return [a for a in authors if a and a not in (".", "..")]

    def _list_books(self, root: RootName, author_rel: str) -> list[str]:
        entries = self._fs.list_dir(root, author_rel, recursive=False)
        books = sorted([_basename(e.rel_path) for e in entries if e.is_dir])
        return [b for b in books if b and b not in (".", "..")]

    def _preflight_book(
        self, root: RootName, author: str, book: str, book_rel: str
    ) -> BookPreflight:
        cover_candidates = self._find_cover_candidates(root, book_rel)
        fingerprint = self._fingerprint_book(root, book_rel)

        # Rename preview is a deterministic placeholder map (identity mapping).
        rename_preview = {book_rel: book_rel}

        return BookPreflight(
            author=author,
            book=book,
            rel_path=book_rel,
            suggested_author=author,
            suggested_title=book,
            cover_candidates=cover_candidates,
            rename_preview=rename_preview,
            fingerprint=fingerprint,
            meta={"id3_majority": None},
        )

    def _find_cover_candidates(self, root: RootName, book_rel: str) -> list[str]:
        entries = self._fs.list_dir(root, book_rel, recursive=True)
        files = [e.rel_path for e in entries if not e.is_dir]
        imgs = []
        for rel in files:
            ext = _ext(rel)
            if ext in _IMG_EXT:
                imgs.append(rel)
        return sorted(imgs)

    def _fingerprint_book(self, root: RootName, book_rel: str) -> BookFingerprint:
        entries = self._fs.list_dir(root, book_rel, recursive=True)
        files = [e.rel_path for e in entries if not e.is_dir]
        items: list[tuple[str, str]] = []
        for rel in sorted(files):
            ext = _ext(rel)
            if ext not in _AUDIO_EXT and ext not in _IMG_EXT:
                continue
            chk = self._fs.checksum(root, rel, algo="sha256")
            items.append((rel, chk))

        h = hashlib.sha256()
        for rel, chk in items:
            h.update(rel.encode("utf-8"))
            h.update(b"\n")
            h.update(chk.encode("utf-8"))
            h.update(b"\n")
        return BookFingerprint(algo="sha256", value=h.hexdigest(), strength="basic")


def _basename(rel_path: str) -> str:
    rel = rel_path.rstrip("/")
    if "/" not in rel:
        return rel
    return rel.split("/")[-1]


def _join(a: str, b: str) -> str:
    if not a or a == ".":
        return b
    return f"{a.rstrip('/')}/{b}"


def _ext(rel_path: str) -> str:
    name = _basename(rel_path).lower()
    if "." not in name:
        return ""
    return "." + name.split(".")[-1]
