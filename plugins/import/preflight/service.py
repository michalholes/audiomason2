"""Preflight (PHASE 0) service for import wizard.

Deterministic and read-only.
All filesystem operations go through file_io capability.

ASCII-only.
"""

from __future__ import annotations

import hashlib
import json
import time
import traceback
from typing import Any

from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import FileEntry, RootName

from .types import (
    BookFingerprint,
    BookPreflight,
    DeepScanState,
    IndexBook,
    IndexItem,
    IndexResult,
    PreflightResult,
    SkippedEntry,
)

_AUDIO_EXT = {".mp3", ".m4a", ".m4b", ".flac", ".wav", ".ogg", ".opus"}
_ARCHIVE_EXT = {".zip", ".rar", ".7z"}
_IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}

# Cache is stored under the file_io JOBS root (not inbox).
CACHE_REL_PATH = "import_wizard/cache_v1.json"


def _duration_ms(t0: float, t1: float) -> int:
    ms = int((t1 - t0) * 1000.0)
    return 0 if ms < 0 else ms


def _shorten_text(s: str, *, max_chars: int = 2000) -> str:
    if len(s) <= max_chars:
        return s
    return s[: max(0, max_chars - 3)] + "..."


def _shorten_traceback(tb: str) -> str:
    tb = tb.strip("\n")
    if not tb:
        return ""
    lines = tb.splitlines()
    lines = lines[-20:]
    return _shorten_text("\n".join(lines), max_chars=2000)


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
        t0 = time.monotonic()
        inputs_summary = {"root": str(root), "source_root_rel_path": source_root_rel_path}

        # Keep legacy boundary events for compatibility.
        _emit_diag("boundary.start", operation="run", data=inputs_summary)

        # Contracted step-level observability.
        _emit_diag(
            "operation.start",
            operation="import.preflight",
            data={
                "wizard": "import",
                "step": "preflight",
                "inputs_summary": inputs_summary,
                "status": "running",
            },
        )

        try:
            authors: list[str] = []
            books: list[BookPreflight] = []
            skipped: list[SkippedEntry] = []

            scan_t0 = time.monotonic()
            _emit_diag(
                "operation.start",
                operation="import.scan",
                data={
                    "wizard": "import",
                    "step": "scan",
                    "inputs_summary": inputs_summary,
                    "status": "running",
                },
            )
            try:
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
            except Exception as e:
                scan_t1 = time.monotonic()
                _emit_diag(
                    "operation.end",
                    operation="import.scan",
                    data={
                        "wizard": "import",
                        "step": "scan",
                        "inputs_summary": inputs_summary,
                        "status": "failed",
                        "duration_ms": _duration_ms(scan_t0, scan_t1),
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "traceback": _shorten_traceback(traceback.format_exc()),
                    },
                )
                raise
            else:
                scan_t1 = time.monotonic()
                _emit_diag(
                    "operation.end",
                    operation="import.scan",
                    data={
                        "wizard": "import",
                        "step": "scan",
                        "inputs_summary": inputs_summary,
                        "status": "succeeded",
                        "duration_ms": _duration_ms(scan_t0, scan_t1),
                        "items_count": len(books),
                        "skipped_count": len(skipped),
                    },
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
        except Exception as e:
            t1 = time.monotonic()
            _emit_diag(
                "operation.end",
                operation="import.preflight",
                data={
                    "wizard": "import",
                    "step": "preflight",
                    "inputs_summary": inputs_summary,
                    "status": "failed",
                    "duration_ms": _duration_ms(t0, t1),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": _shorten_traceback(traceback.format_exc()),
                },
            )
            _emit_diag(
                "boundary.end",
                operation="run",
                data={
                    "root": str(root),
                    "source_root_rel_path": source_root_rel_path,
                    "status": "failed",
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )
            raise

        t1 = time.monotonic()
        _emit_diag(
            "operation.end",
            operation="import.preflight",
            data={
                "wizard": "import",
                "step": "preflight",
                "inputs_summary": inputs_summary,
                "status": "succeeded",
                "duration_ms": _duration_ms(t0, t1),
                "authors_n": len(authors),
                "books_n": len(books),
                "skipped_n": len(skipped),
            },
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

    def fast_index(self, root: RootName, source_root_rel_path: str) -> IndexResult:
        """Fast 2-level index for the import wizard start screen.

        PHASE 0 only. No recursive listing, no checksums, no audio reads.
        """

        t0 = time.monotonic()
        inputs_summary = {"root": str(root), "source_root_rel_path": source_root_rel_path}

        _emit_diag("boundary.start", operation="fast_index", data=inputs_summary)
        _emit_diag(
            "operation.start",
            operation="import.fast_index",
            data={
                "wizard": "import",
                "step": "fast_index",
                "inputs_summary": inputs_summary,
                "status": "running",
            },
        )

        try:
            cache = self._load_cache()
            idx = self._build_fast_index(root, source_root_rel_path)
            signature = idx["signature"]
            cached_sig = str(cache.get("signature") or "")
            changed = bool(signature != cached_sig)

            if (not changed) and isinstance(cache.get("index"), dict):
                # Cache-first return.
                res = self._index_from_cache(cache, changed=False)
            else:
                # Update cache with new index. Deep enrichment is triggered separately.
                cache["signature"] = signature
                cache["index"] = idx
                cache["last_scan_ts"] = float(time.time())
                deep = cache.get("deep", {}) if isinstance(cache.get("deep"), dict) else {}
                deep_state = str(deep.get("state") or "idle")
                last_enriched_sig = str(deep.get("signature") or "")
                if signature != last_enriched_sig:
                    deep_state = "pending"
                deep["state"] = deep_state
                deep["pending_signature"] = signature
                cache["deep"] = deep
                self._save_cache(cache)
                res = self._index_from_cache(cache, changed=changed)

        except Exception as e:
            t1 = time.monotonic()
            _emit_diag(
                "operation.end",
                operation="import.fast_index",
                data={
                    "wizard": "import",
                    "step": "fast_index",
                    "inputs_summary": inputs_summary,
                    "status": "failed",
                    "duration_ms": _duration_ms(t0, t1),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": _shorten_traceback(traceback.format_exc()),
                },
            )
            _emit_diag(
                "boundary.end",
                operation="fast_index",
                data={"status": "failed", "error_type": type(e).__name__, "error_message": str(e)},
            )
            raise

        t1 = time.monotonic()
        _emit_diag(
            "operation.end",
            operation="import.fast_index",
            data={
                "wizard": "import",
                "step": "fast_index",
                "inputs_summary": inputs_summary,
                "status": "succeeded",
                "duration_ms": _duration_ms(t0, t1),
                "authors_n": len(res.authors),
                "books_n": len(res.books),
                "root_items_n": len(res.root_items),
                "changed": bool(res.changed),
            },
        )
        _emit_diag("boundary.end", operation="fast_index", data={"status": "succeeded"})
        return res

    def get_deep_scan_state(self) -> DeepScanState:
        cache = self._load_cache()
        deep = cache.get("deep", {}) if isinstance(cache.get("deep"), dict) else {}
        return DeepScanState(
            state=str(deep.get("state") or "idle"),
            signature=str(deep.get("signature") or "") or None,
            last_scan_ts=_to_float_opt(deep.get("last_scan_ts")),
            scanned_items=int(deep.get("scanned_items") or 0),
            total_items=int(deep.get("total_items") or 0),
            last_error=str(deep.get("last_error") or "") or None,
        )

    def run_deep_enrichment_if_needed(self, root: RootName, source_root_rel_path: str) -> None:
        """Run background deep enrichment if the index signature changed.

        PHASE 0 only. May perform recursive listing and metadata detection,
        but must remain read-only.
        """

        inputs_summary = {"root": str(root), "source_root_rel_path": source_root_rel_path}

        # Check whether we have pending work.
        cache = self._load_cache()
        idx = cache.get("index")
        if not isinstance(idx, dict):
            # No index -> build one first.
            _ = self.fast_index(root, source_root_rel_path)
            cache = self._load_cache()
            idx = cache.get("index")
            if not isinstance(idx, dict):
                return

        signature = str(cache.get("signature") or "")
        deep = cache.get("deep", {}) if isinstance(cache.get("deep"), dict) else {}
        deep_state = str(deep.get("state") or "idle")
        last_enriched_sig = str(deep.get("signature") or "")

        if not signature or signature == last_enriched_sig:
            # Already enriched for current signature.
            if deep_state in {"pending", "failed"}:
                deep["state"] = "done"
                cache["deep"] = deep
                self._save_cache(cache)
            return

        if deep_state == "running":
            return

        t0 = time.monotonic()
        _emit_diag(
            "operation.start",
            operation="import.deep_enrichment",
            data={"inputs_summary": inputs_summary},
        )
        _emit_diag("boundary.start", operation="deep_enrichment", data=inputs_summary)

        try:
            books = idx.get("books", [])
            if not isinstance(books, list):
                books = []
            total_items = len(books)

            deep.update(
                {
                    "state": "running",
                    "signature": None,
                    "pending_signature": signature,
                    "last_scan_ts": float(time.time()),
                    "scanned_items": 0,
                    "total_items": int(total_items),
                    "last_error": None,
                }
            )
            cache["deep"] = deep
            self._save_cache(cache)

            enrichment = cache.get("enrichment", {})
            if not isinstance(enrichment, dict):
                enrichment = {}

            # Delta set: process only books whose ref is missing or marked for rescan.
            # We use the stored per-book signature derived from rel_path+stat.
            current_book_sigs: dict[str, str] = {}
            for b in books:
                if not isinstance(b, dict):
                    continue
                book_ref = str(b.get("book_ref") or "")
                rel_path = str(b.get("rel_path") or "")
                unit_type = str(b.get("unit_type") or "")
                if not book_ref or not rel_path or unit_type not in {"dir", "file"}:
                    continue
                current_book_sigs[book_ref] = self._book_signature(
                    root, rel_path, unit_type=unit_type
                )

            removed_refs = [k for k in enrichment if k not in current_book_sigs]
            for k in removed_refs:
                enrichment.pop(k, None)

            scanned = 0
            for b in books:
                if not isinstance(b, dict):
                    continue
                book_ref = str(b.get("book_ref") or "")
                rel_path = str(b.get("rel_path") or "")
                unit_type = str(b.get("unit_type") or "")
                if not book_ref or not rel_path or unit_type not in {"dir", "file"}:
                    continue

                book_sig = current_book_sigs.get(book_ref, "")
                prev = enrichment.get(book_ref)
                prev_sig = ""
                if isinstance(prev, dict):
                    prev_sig = str(prev.get("_sig") or "")

                if book_sig and book_sig == prev_sig:
                    scanned += 1
                    deep["scanned_items"] = int(scanned)
                    cache["deep"] = deep
                    self._save_cache(cache)
                    continue

                _emit_diag(
                    "operation.start",
                    operation="import.deep_enrichment.book",
                    data={"book_ref": book_ref, "rel_path": rel_path, "unit_type": unit_type},
                )

                try:
                    enriched = self._enrich_book(
                        root, source_root_rel_path, rel_path, unit_type=unit_type
                    )
                    enriched["_sig"] = book_sig
                    enrichment[book_ref] = enriched
                except Exception as e:
                    _emit_diag(
                        "operation.end",
                        operation="import.deep_enrichment.book",
                        data={
                            "book_ref": book_ref,
                            "rel_path": rel_path,
                            "unit_type": unit_type,
                            "status": "failed",
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                            "traceback": _shorten_traceback(traceback.format_exc()),
                        },
                    )
                    raise
                else:
                    _emit_diag(
                        "operation.end",
                        operation="import.deep_enrichment.book",
                        data={
                            "book_ref": book_ref,
                            "rel_path": rel_path,
                            "unit_type": unit_type,
                            "status": "succeeded",
                        },
                    )

                scanned += 1
                deep["scanned_items"] = int(scanned)
                cache["enrichment"] = enrichment
                cache["deep"] = deep
                self._save_cache(cache)

            deep.update(
                {"state": "done", "signature": signature, "last_scan_ts": float(time.time())}
            )
            cache["deep"] = deep
            cache["enrichment"] = enrichment
            self._save_cache(cache)

        except Exception as e:
            deep = cache.get("deep", {}) if isinstance(cache.get("deep"), dict) else {}
            deep.update(
                {
                    "state": "failed",
                    "last_error": f"{type(e).__name__}: {e}",
                    "last_scan_ts": float(time.time()),
                }
            )
            cache["deep"] = deep
            self._save_cache(cache)
            t1 = time.monotonic()
            _emit_diag(
                "operation.end",
                operation="import.deep_enrichment",
                data={
                    "inputs_summary": inputs_summary,
                    "status": "failed",
                    "duration_ms": _duration_ms(t0, t1),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": _shorten_traceback(traceback.format_exc()),
                },
            )
            _emit_diag(
                "boundary.end",
                operation="deep_enrichment",
                data={"status": "failed", "error_type": type(e).__name__, "error_message": str(e)},
            )
            raise
        else:
            t1 = time.monotonic()
            _emit_diag(
                "operation.end",
                operation="import.deep_enrichment",
                data={
                    "inputs_summary": inputs_summary,
                    "status": "succeeded",
                    "duration_ms": _duration_ms(t0, t1),
                },
            )
            _emit_diag("boundary.end", operation="deep_enrichment", data={"status": "succeeded"})

    def _load_cache(self) -> dict[str, Any]:
        try:
            with self._fs.open_read(RootName.JOBS, CACHE_REL_PATH) as f:
                raw = f.read()
            if not raw:
                return {}
            obj = json.loads(raw.decode("utf-8"))
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}

    def _save_cache(self, cache: dict[str, Any]) -> None:
        try:
            payload = json.dumps(cache, sort_keys=True, separators=(",", ":")).encode("utf-8")
            with self._fs.open_write(
                RootName.JOBS, CACHE_REL_PATH, overwrite=True, mkdir_parents=True
            ) as f:
                f.write(payload)
        except Exception:
            return

    def _index_from_cache(self, cache: dict[str, Any], *, changed: bool) -> IndexResult:
        idx = cache.get("index", {}) if isinstance(cache.get("index"), dict) else {}
        deep = cache.get("deep", {}) if isinstance(cache.get("deep"), dict) else {}
        enrichment = (
            cache.get("enrichment", {}) if isinstance(cache.get("enrichment"), dict) else {}
        )

        books: list[IndexBook] = []
        for b in idx.get("books", []) if isinstance(idx.get("books"), list) else []:
            if not isinstance(b, dict):
                continue
            book_ref = str(b.get("book_ref") or "")
            unit_type = str(b.get("unit_type") or "")
            author = str(b.get("author") or "")
            book = str(b.get("book") or "")
            rel_path = str(b.get("rel_path") or "")
            if not book_ref or not rel_path:
                continue
            enrich = enrichment.get(book_ref)
            if not isinstance(enrich, dict):
                enrich = {}
            books.append(
                IndexBook(
                    book_ref=book_ref,
                    unit_type=unit_type,
                    author=author,
                    book=book,
                    rel_path=rel_path,
                    suggested_author=_opt_str(enrich.get("suggested_author")),
                    suggested_title=_opt_str(enrich.get("suggested_title")),
                    cover_candidates=list(enrich.get("cover_candidates") or [])
                    if enrich.get("cover_candidates") is not None
                    else None,
                    rename_preview=enrich.get("rename_preview")
                    if isinstance(enrich.get("rename_preview"), dict)
                    else None,
                    fingerprint=_fingerprint_from_dict(enrich.get("fingerprint")),
                    meta=enrich.get("meta") if isinstance(enrich.get("meta"), dict) else None,
                )
            )

        root_items: list[IndexItem] = []
        for it in idx.get("root_items", []) if isinstance(idx.get("root_items"), list) else []:
            if not isinstance(it, dict):
                continue
            root_items.append(
                IndexItem(
                    rel_path=str(it.get("rel_path") or ""),
                    item_type=str(it.get("item_type") or ""),
                    size=_to_int_opt(it.get("size")),
                    mtime=_to_float_opt(it.get("mtime")),
                )
            )

        authors = (
            [str(a) for a in (idx.get("authors") or [])]
            if isinstance(idx.get("authors"), list)
            else []
        )
        authors = sorted([a for a in authors if a])

        state = DeepScanState(
            state=str(deep.get("state") or "idle"),
            signature=_opt_str(deep.get("signature")),
            last_scan_ts=_to_float_opt(deep.get("last_scan_ts")),
            scanned_items=int(deep.get("scanned_items") or 0),
            total_items=int(deep.get("total_items") or 0),
            last_error=_opt_str(deep.get("last_error")),
        )

        return IndexResult(
            source_root_rel_path=str(idx.get("source_root_rel_path") or "."),
            signature=str(cache.get("signature") or ""),
            changed=bool(changed),
            last_scan_ts=_to_float_opt(cache.get("last_scan_ts")),
            deep_scan_state=state,
            root_items=root_items,
            authors=authors,
            books=sorted(books, key=lambda b: (b.author, b.book, b.rel_path)),
        )

    def _build_fast_index(self, root: RootName, source_root_rel_path: str) -> dict[str, Any]:
        root_entries = self._fs.list_dir(root, source_root_rel_path, recursive=False)
        items_for_sig: list[dict[str, Any]] = []
        root_items: list[dict[str, Any]] = []
        books: list[dict[str, Any]] = []
        authors: set[str] = set()

        def _sig_add(e: FileEntry) -> None:
            items_for_sig.append(
                {
                    "rel_path": str(e.rel_path),
                    "is_dir": bool(e.is_dir),
                    "size": int(e.size) if e.size is not None else 0,
                    "mtime": float(e.mtime) if e.mtime is not None else 0.0,
                }
            )

        for entry in sorted(root_entries, key=lambda e: e.rel_path):
            name = _basename(entry.rel_path)
            if not name or name in (".", ".."):
                continue
            _sig_add(entry)

            if entry.is_dir:
                dir_rel = entry.rel_path.rstrip("/")
                child_entries = self._fs.list_dir(root, dir_rel, recursive=False)
                # include second level in signature
                for ce in sorted(child_entries, key=lambda e: e.rel_path):
                    n2 = _basename(ce.rel_path)
                    if not n2 or n2 in (".", ".."):
                        continue
                    _sig_add(ce)

                child_dirs = sorted(
                    [
                        _basename(e.rel_path)
                        for e in child_entries
                        if e.is_dir and _basename(e.rel_path) not in ("", ".", "..")
                    ]
                )
                if child_dirs:
                    # author directory with book children
                    root_items.append(
                        {
                            "rel_path": dir_rel,
                            "item_type": "author_dir",
                            "size": entry.size,
                            "mtime": entry.mtime,
                        }
                    )
                    author = name
                    authors.add(author)
                    for book in child_dirs:
                        book_rel = _join(dir_rel, book)
                        books.append(
                            {
                                "book_ref": _book_ref(source_root_rel_path, book_rel),
                                "unit_type": "dir",
                                "author": author,
                                "book": book,
                                "rel_path": book_rel,
                            }
                        )
                else:
                    # root-level book directory
                    root_items.append(
                        {
                            "rel_path": dir_rel,
                            "item_type": "book_dir",
                            "size": entry.size,
                            "mtime": entry.mtime,
                        }
                    )
                    books.append(
                        {
                            "book_ref": _book_ref(source_root_rel_path, dir_rel),
                            "unit_type": "dir",
                            "author": "",
                            "book": name,
                            "rel_path": dir_rel,
                        }
                    )
            else:
                ext = _ext(entry.rel_path)
                item_type = "other_file"
                if ext in _AUDIO_EXT:
                    item_type = "audio_file"
                    books.append(
                        {
                            "book_ref": _book_ref(source_root_rel_path, entry.rel_path),
                            "unit_type": "file",
                            "author": "",
                            "book": _stem(entry.rel_path),
                            "rel_path": entry.rel_path,
                        }
                    )
                elif ext == ".zip":
                    item_type = "container_zip"
                elif ext == ".rar":
                    item_type = "container_rar"
                root_items.append(
                    {
                        "rel_path": entry.rel_path,
                        "item_type": item_type,
                        "size": entry.size,
                        "mtime": entry.mtime,
                    }
                )

        authors_list = sorted(authors)
        # book-only label is represented by empty author; web layer adds label.
        sig_items = sorted(items_for_sig, key=lambda x: str(x.get("rel_path") or ""))
        idx_obj = {
            "source_root_rel_path": source_root_rel_path,
            "root_items": sorted(root_items, key=lambda x: str(x.get("rel_path") or "")),
            "authors": authors_list,
            "books": sorted(
                books,
                key=lambda b: (
                    str(b.get("author") or ""),
                    str(b.get("book") or ""),
                    str(b.get("rel_path") or ""),
                ),
            ),
            "signature_items": sig_items,
        }
        signature = _stable_signature(sig_items)
        idx_obj["signature"] = signature
        return idx_obj

    def _book_signature(self, root: RootName, rel_path: str, *, unit_type: str) -> str:
        if unit_type == "file":
            st = self._fs.stat(root, rel_path)
            file_items = [
                {
                    "rel_path": rel_path,
                    "is_dir": False,
                    "size": int(st.size),
                    "mtime": float(st.mtime),
                }
            ]
            return _stable_signature(file_items)

        entries = self._fs.list_dir(root, rel_path, recursive=True)
        items: list[dict[str, Any]] = []
        for e in entries:
            if e.is_dir:
                continue
            ext = _ext(e.rel_path)
            if ext in _AUDIO_EXT or ext in _IMG_EXT:
                items.append(
                    {
                        "rel_path": str(e.rel_path),
                        "is_dir": False,
                        "size": int(e.size) if e.size is not None else 0,
                        "mtime": float(e.mtime) if e.mtime is not None else 0.0,
                    }
                )
        return _stable_signature(sorted(items, key=lambda x: str(x.get("rel_path") or "")))

    def _enrich_book(
        self,
        root: RootName,
        source_root_rel_path: str,
        rel_path: str,
        *,
        unit_type: str,
    ) -> dict[str, Any]:
        # This is intentionally minimal for Issue 500
        # (pipeline correctness over full enrichment parity).
        if unit_type == "dir":
            cover_candidates = self._find_cover_candidates(root, rel_path)
            fingerprint = self._fingerprint_stat_based_dir(root, rel_path)
            return {
                "suggested_author": None,
                "suggested_title": _basename(rel_path),
                "cover_candidates": cover_candidates,
                "rename_preview": {rel_path: rel_path},
                "fingerprint": _fingerprint_to_dict(fingerprint),
                "meta": {"id3_majority": None},
            }

        fingerprint = self._fingerprint_stat_based_file(root, rel_path)
        return {
            "suggested_author": None,
            "suggested_title": _stem(rel_path),
            "cover_candidates": [],
            "rename_preview": {rel_path: rel_path},
            "fingerprint": _fingerprint_to_dict(fingerprint),
            "meta": {"id3_majority": None},
        }

    def _fingerprint_stat_based_dir(self, root: RootName, book_rel: str) -> BookFingerprint:
        entries = self._fs.list_dir(root, book_rel, recursive=True)
        items: list[tuple[str, int, float]] = []
        for e in entries:
            if e.is_dir:
                continue
            ext = _ext(e.rel_path)
            if ext not in _AUDIO_EXT and ext not in _IMG_EXT:
                continue
            items.append((e.rel_path, int(e.size or 0), float(e.mtime or 0.0)))

        h = hashlib.sha256()
        for rel, size, mtime in sorted(items):
            h.update(rel.encode("utf-8"))
            h.update(b"\n")
            h.update(str(size).encode("utf-8"))
            h.update(b"\n")
            h.update(f"{mtime:.6f}".encode())
            h.update(b"\n")
        return BookFingerprint(algo="sha256", value=h.hexdigest(), strength="basic")

    def _fingerprint_stat_based_file(self, root: RootName, file_rel: str) -> BookFingerprint:
        st = self._fs.stat(root, file_rel)
        h = hashlib.sha256()
        h.update(file_rel.encode("utf-8"))
        h.update(b"\n")
        h.update(str(int(st.size)).encode("utf-8"))
        h.update(b"\n")
        h.update(f"{float(st.mtime):.6f}".encode())
        h.update(b"\n")
        return BookFingerprint(algo="sha256", value=h.hexdigest(), strength="basic")

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


def _opt_str(v: Any) -> str | None:
    if v is None:
        return None
    if not isinstance(v, str):
        v = str(v)
    v = v.strip()
    return v or None


def _to_int_opt(v: Any) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            try:
                return int(float(s))
            except ValueError:
                return None
    try:
        return int(v)
    except Exception:
        return None


def _to_float_opt(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    try:
        return float(v)
    except Exception:
        return None


def _fingerprint_to_dict(fp: BookFingerprint | None) -> dict[str, Any] | None:
    if fp is None:
        return None
    return {"algo": fp.algo, "value": fp.value, "strength": fp.strength}


def _fingerprint_from_dict(v: Any) -> BookFingerprint | None:
    if not isinstance(v, dict):
        return None
    algo = v.get("algo")
    value = v.get("value")
    strength = v.get("strength")
    if not isinstance(algo, str) or not isinstance(value, str):
        return None
    if not isinstance(strength, str) or not strength:
        strength = "basic"
    return BookFingerprint(algo=algo, value=value, strength=strength)


def _stable_signature(items: list[dict[str, Any]]) -> str:
    payload = json.dumps(items, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    h = hashlib.sha256()
    h.update(payload.encode("utf-8"))
    return h.hexdigest()


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
