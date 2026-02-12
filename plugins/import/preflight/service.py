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

from .types import BookFingerprint, BookPreflight, PreflightResult, SkippedEntry

_AUDIO_EXT = {".mp3", ".m4a", ".m4b", ".flac", ".wav", ".ogg", ".opus"}
_ARCHIVE_EXT = {".zip", ".rar", ".7z"}
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

        authors: list[str] = []
        books: list[BookPreflight] = []
        skipped: list[SkippedEntry] = []

        root_entries = self._fs.list_dir(root, source_root_rel_path, recursive=False)
        # Deterministic traversal order.
        for entry in sorted(root_entries, key=lambda e: e.rel_path):
            name = _basename(entry.rel_path)
            if not name or name in (".", ".."):
                continue

            if entry.is_dir:
                dir_rel = entry.rel_path.rstrip("/")
                child_entries = self._fs.list_dir(root, dir_rel, recursive=False)
                child_dirs = sorted(
                    [
                        _basename(e.rel_path)
                        for e in child_entries
                        if e.is_dir and _basename(e.rel_path) not in ("", ".", "..")
                    ]
                )

                # Mixed inbox layout support:
                # - if the directory contains at least one subdirectory, treat it as an
                #   author directory (author/book)
                # - otherwise treat it as a single-level book directory
                if child_dirs:
                    author = name
                    authors.append(author)
                    author_rel = dir_rel
                    # Any files directly under an author directory are not book units.
                    for e in child_entries:
                        if not e.is_dir:
                            skipped.append(
                                SkippedEntry(
                                    rel_path=e.rel_path,
                                    entry_type="file",
                                    reason="unexpected_file_in_author_dir",
                                )
                            )

                    for book in child_dirs:
                        book_rel = _join(author_rel, book)
                        books.append(
                            self._preflight_dir(
                                root,
                                source_root_rel_path,
                                author=author,
                                book=book,
                                book_rel=book_rel,
                            )
                        )
                else:
                    # Single-level book directory in inbox.
                    books.append(
                        self._preflight_dir(
                            root,
                            source_root_rel_path,
                            author="",
                            book=name,
                            book_rel=dir_rel,
                        )
                    )
            else:
                ext = _ext(entry.rel_path)
                if ext in _ARCHIVE_EXT or ext in _AUDIO_EXT:
                    books.append(
                        self._preflight_file(
                            root,
                            source_root_rel_path,
                            author="",
                            book=_stem(entry.rel_path),
                            file_rel=entry.rel_path,
                        )
                    )
                else:
                    skipped.append(
                        SkippedEntry(
                            rel_path=entry.rel_path,
                            entry_type="file",
                            reason="unsupported_file_ext",
                        )
                    )

        authors = sorted(set(authors))
        books.sort(key=lambda b: (b.author, b.book, b.rel_path))
        skipped.sort(key=lambda s: s.rel_path)

        res = PreflightResult(
            source_root_rel_path=source_root_rel_path,
            authors=authors,
            books=books,
            skipped=skipped,
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

    def _preflight_dir(
        self,
        root: RootName,
        source_root_rel_path: str,
        *,
        author: str,
        book: str,
        book_rel: str,
    ) -> BookPreflight:
        cover_candidates = self._find_cover_candidates(root, book_rel)
        fingerprint = self._fingerprint_dir(root, book_rel)

        # Rename preview is a deterministic placeholder map (identity mapping).
        rename_preview = {book_rel: book_rel}

        return BookPreflight(
            book_ref=_book_ref(source_root_rel_path, book_rel),
            unit_type="dir",
            author=author,
            book=book,
            rel_path=book_rel,
            suggested_author=author or None,
            suggested_title=book,
            cover_candidates=cover_candidates,
            rename_preview=rename_preview,
            fingerprint=fingerprint,
            meta={"id3_majority": None},
        )

    def _preflight_file(
        self,
        root: RootName,
        source_root_rel_path: str,
        *,
        author: str,
        book: str,
        file_rel: str,
    ) -> BookPreflight:
        fingerprint = self._fingerprint_file(root, file_rel)
        return BookPreflight(
            book_ref=_book_ref(source_root_rel_path, file_rel),
            unit_type="file",
            author=author,
            book=book,
            rel_path=file_rel,
            suggested_author=author or None,
            suggested_title=book,
            cover_candidates=[],
            rename_preview={file_rel: file_rel},
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

    def _fingerprint_dir(self, root: RootName, book_rel: str) -> BookFingerprint:
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

    def _fingerprint_file(self, root: RootName, file_rel: str) -> BookFingerprint:
        chk = self._fs.checksum(root, file_rel, algo="sha256")
        h = hashlib.sha256()
        h.update(file_rel.encode("utf-8"))
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


def _stem(rel_path: str) -> str:
    name = _basename(rel_path)
    if "." not in name:
        return name
    return name.rsplit(".", 1)[0]


def _book_ref(source_root_rel_path: str, rel_path: str) -> str:
    """Stable unit identifier for this discovery.

    Scoped to source root path and the discovered rel_path.
    """

    h = hashlib.sha256()
    h.update(source_root_rel_path.encode("utf-8"))
    h.update(b"\n")
    h.update(rel_path.encode("utf-8"))
    h.update(b"\n")
    return "book_" + h.hexdigest()[:24]
