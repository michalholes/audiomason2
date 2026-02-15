"""Preflight (PHASE 0) service for import wizard.

Deterministic and read-only.
All filesystem operations go through file_io capability.

ASCII-only.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
import time
import traceback
from typing import Any

from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus
from plugins.file_io.service.service import FileService
from plugins.file_io.service.types import FileEntry, RootName

from ..processed_registry.service import build_book_fingerprint_key
from .types import (
    BookFingerprint,
    BookPreflight,
    DeepScanState,
    Id3MajorityConfig,
    IndexBook,
    IndexItem,
    IndexResult,
    LookupStatus,
    PlanPreview,
    PreflightResult,
    SkippedEntry,
)


def _book_fingerprint_from_identity_key(identity_key: str) -> BookFingerprint:
    algo, _, value = str(identity_key or "").partition(":")
    algo = algo.strip() or "unknown"
    value = value.strip()
    return BookFingerprint(algo=algo, value=value, strength="basic")


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

    def __init__(
        self,
        fs: FileService,
        *,
        id3_majority: Id3MajorityConfig | None = None,
        enable_lookup: bool = True,
    ) -> None:
        self._fs = fs
        self._id3_majority = id3_majority or Id3MajorityConfig()
        self._enable_lookup = bool(enable_lookup)

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

    def plan_preview_for_book(
        self,
        root: RootName,
        source_root_rel_path: str,
        *,
        book_ref: str,
        rel_path: str,
        unit_type: str,
        author: str,
        book: str,
    ) -> PlanPreview:
        """Build plan/preview for a selected unit.

        This method is intended for CLI PHASE 1 after selection. Deep enrichment is
        best-effort and MUST NOT block the initial selection screen.
        """

        # Best-effort: ensure cache exists for the current signature.
        with contextlib.suppress(Exception):
            self.fast_index(root, source_root_rel_path)

        proposed_author = str(author or "").strip() or ""
        proposed_title = str(book or "").strip() or ""

        lookup = LookupStatus(status="disabled")
        rename_preview: dict[str, str] = {str(rel_path): str(rel_path)}
        cover_candidates: list[str] | None = None
        fingerprint = None
        meta: dict[str, Any] | None = None

        try:
            enriched = self._enrich_book(
                root,
                source_root_rel_path,
                rel_path,
                unit_type=str(unit_type or "dir"),
            )
            if isinstance(enriched, dict):
                proposed_author = (
                    str(enriched.get("suggested_author") or "").strip() or proposed_author
                )
                proposed_title = (
                    str(enriched.get("suggested_title") or "").strip() or proposed_title
                )

                rp = enriched.get("rename_preview")
                if isinstance(rp, dict) and rp:
                    rename_preview = {str(k): str(v) for k, v in rp.items()}

                cc = enriched.get("cover_candidates")
                if isinstance(cc, list):
                    cover_candidates = [str(x) for x in cc if str(x)]

                fingerprint = _fingerprint_from_dict(enriched.get("fingerprint"))
                meta = enriched.get("meta") if isinstance(enriched.get("meta"), dict) else None

                # Lookup status is best-effort.
                if not self._enable_lookup:
                    lookup = LookupStatus(status="disabled")
                else:
                    lk = None
                    if isinstance(meta, dict):
                        lk = meta.get("lookup")
                    if isinstance(lk, dict) and lk:
                        lookup = LookupStatus(status="matched", source=str(lk.get("source") or ""))
                    else:
                        lookup = LookupStatus(status="unknown")

                # Persist enrichment into the cache (best-effort) so subsequent calls are fast.
                try:
                    cache = self._load_cache()
                    enrichment = (
                        cache.get("enrichment", {})
                        if isinstance(cache.get("enrichment"), dict)
                        else {}
                    )
                    book_sig = self._book_signature(
                        root, rel_path, unit_type=str(unit_type or "dir")
                    )
                    enriched2 = dict(enriched)
                    enriched2["_sig"] = book_sig
                    enrichment[str(book_ref)] = enriched2
                    cache["enrichment"] = enrichment
                    self._save_cache(cache)
                except Exception:
                    pass

        except Exception as e:
            if self._enable_lookup:
                lookup = LookupStatus(status="error", error=f"{type(e).__name__}: {e}")

        return PlanPreview(
            book_ref=str(book_ref),
            unit_type=str(unit_type or "dir"),
            rel_path=str(rel_path),
            proposed_author=str(proposed_author or ""),
            proposed_title=str(proposed_title or ""),
            lookup=lookup,
            rename_preview=rename_preview,
            cover_candidates=cover_candidates,
            fingerprint=fingerprint,
            meta=meta,
        )

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
        if unit_type == "dir":
            return self._enrich_book_dir(root, rel_path)
        return self._enrich_book_file(root, rel_path)

    def _enrich_book_dir(self, root: RootName, book_rel: str) -> dict[str, Any]:
        audio_files = self._list_audio_files(root, book_rel)
        id3 = self._id3_majority_vote(root, audio_files)

        # Covers: embedded APIC + directory images.
        dir_imgs = self._find_cover_candidates(root, book_rel)
        apic_markers = self._find_apic_markers(root, audio_files)
        cover_candidates = sorted(set(dir_imgs + apic_markers))

        rename_preview = self._build_rename_preview(root, audio_files)

        identity_key = build_book_fingerprint_key(
            self._fs,
            source_root=root,
            book_rel_path=book_rel,
            unit_type="dir",
        )
        fp_basic = _book_fingerprint_from_identity_key(identity_key)

        meta: dict[str, Any] = {
            "id3_majority": id3,
            "fingerprint_basic": _fingerprint_to_dict(fp_basic),
        }

        # Optional lookup integration (best-effort, fail-safe).
        if self._enable_lookup:
            meta["lookup"] = self._lookup_best_effort(id3)

        suggested_author = _opt_str((id3 or {}).get("author"))
        suggested_title = _opt_str((id3 or {}).get("album")) or _basename(book_rel)

        return {
            "suggested_author": suggested_author,
            "suggested_title": suggested_title,
            "cover_candidates": cover_candidates,
            "rename_preview": rename_preview,
            "fingerprint": _fingerprint_to_dict(fp_basic),
            "meta": meta,
        }

    def _enrich_book_file(self, root: RootName, file_rel: str) -> dict[str, Any]:
        audio_files = [file_rel] if _ext(file_rel) in _AUDIO_EXT else []
        id3 = self._id3_majority_vote(root, audio_files)
        apic_markers = self._find_apic_markers(root, audio_files)

        rename_preview = (
            self._build_rename_preview(root, audio_files) if audio_files else {file_rel: file_rel}
        )

        identity_key = build_book_fingerprint_key(
            self._fs,
            source_root=root,
            book_rel_path=file_rel,
            unit_type="file",
        )
        fp_basic = _book_fingerprint_from_identity_key(identity_key)
        meta: dict[str, Any] = {
            "id3_majority": id3,
            "fingerprint_basic": _fingerprint_to_dict(fp_basic),
        }
        if self._enable_lookup:
            meta["lookup"] = self._lookup_best_effort(id3)

        suggested_title = _opt_str((id3 or {}).get("title")) or _stem(file_rel)
        suggested_author = _opt_str((id3 or {}).get("author"))

        return {
            "suggested_author": suggested_author,
            "suggested_title": suggested_title,
            "cover_candidates": sorted(set(apic_markers)),
            "rename_preview": rename_preview,
            "fingerprint": _fingerprint_to_dict(fp_basic),
            "meta": meta,
        }

    def _preflight_dir(
        self,
        root: RootName,
        source_root_rel_path: str,
        *,
        author: str,
        book: str,
        book_rel: str,
    ) -> BookPreflight:
        enrich = self._enrich_book_dir(root, book_rel)

        return BookPreflight(
            book_ref=_book_ref(source_root_rel_path, book_rel),
            unit_type="dir",
            author=author,
            book=book,
            rel_path=book_rel,
            suggested_author=_opt_str(enrich.get("suggested_author")) or (author or None),
            suggested_title=_opt_str(enrich.get("suggested_title")) or book,
            cover_candidates=list(enrich.get("cover_candidates") or []),
            rename_preview=enrich.get("rename_preview")
            if isinstance(enrich.get("rename_preview"), dict)
            else None,
            fingerprint=_fingerprint_from_dict(enrich.get("fingerprint")),
            meta=enrich.get("meta") if isinstance(enrich.get("meta"), dict) else None,
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
        enrich = self._enrich_book_file(root, file_rel)
        return BookPreflight(
            book_ref=_book_ref(source_root_rel_path, file_rel),
            unit_type="file",
            author=author,
            book=book,
            rel_path=file_rel,
            suggested_author=_opt_str(enrich.get("suggested_author")) or (author or None),
            suggested_title=_opt_str(enrich.get("suggested_title")) or book,
            cover_candidates=list(enrich.get("cover_candidates") or []),
            rename_preview=enrich.get("rename_preview")
            if isinstance(enrich.get("rename_preview"), dict)
            else None,
            fingerprint=_fingerprint_from_dict(enrich.get("fingerprint")),
            meta=enrich.get("meta") if isinstance(enrich.get("meta"), dict) else None,
        )

    def _read_id3v2_prefix(self, root: RootName, rel_path: str) -> bytes:
        """Read the full ID3v2 tag prefix for MP3 files.

        Returns empty bytes when no ID3v2 tag is present or on read failure.
        """

        try:
            with self._fs.open_read(root, rel_path) as f:
                head = f.read(10)
                if len(head) != 10 or head[:3] != b"ID3":
                    return b""
                size = _id3v2_synchsafe_to_int(head[6:10])
                # Hard cap for safety and determinism.
                if size < 0 or size > 8 * 1024 * 1024:
                    return b""
                body = f.read(int(size))
                return head + body
        except Exception:
            return b""

    def _list_audio_files(self, root: RootName, book_rel: str) -> list[str]:
        entries = self._fs.list_dir(root, book_rel, recursive=True)
        files = [e.rel_path for e in entries if (not e.is_dir) and _ext(e.rel_path) in _AUDIO_EXT]
        return sorted(files)

    def _find_apic_markers(self, root: RootName, audio_files: list[str]) -> list[str]:
        markers: list[str] = []
        for rel in audio_files:
            if _ext(rel) != ".mp3":
                continue
            apics = _id3v2_apic_hashes(self._read_id3v2_prefix(root, rel))
            for h in apics:
                markers.append(f"apic:sha256:{h}")
        return sorted(set(markers))

    def _build_rename_preview(self, root: RootName, audio_files: list[str]) -> dict[str, str]:
        if not audio_files:
            return {}

        items: list[tuple[str, tuple[int, int, tuple[Any, ...]], str, int | None]] = []
        for rel in audio_files:
            ext = _ext(rel)
            stem = _stem(rel)
            title = None
            trk = None
            if ext == ".mp3":
                tags = _id3v2_text_frames(self._read_id3v2_prefix(root, rel))
                title = _opt_str(tags.get("TIT2"))
                trk = _parse_track_number(tags.get("TRCK"))

            fname_num = _parse_track_number(stem)
            if trk is not None:
                key = (0, int(trk), _natural_key(title or stem))
            elif fname_num is not None:
                key = (1, int(fname_num), _natural_key(stem))
            else:
                key = (2, 0, _natural_key(stem))
            explicit_num = (
                int(trk) if trk is not None else (int(fname_num) if fname_num is not None else None)
            )
            items.append((rel, key, title or stem, explicit_num))

        items.sort(key=lambda x: x[1])
        max_explicit = max([n for (_r, _k, _t, n) in items if n is not None] or [0])
        width = max(2, len(str(max(len(items), max_explicit))))

        preview: dict[str, str] = {}
        used: set[int] = set()
        next_auto = 1
        for rel, _k, title, explicit_num in items:
            dir_part = "/".join(rel.split("/")[:-1])
            safe_title = _sanitize_filename(title)
            if explicit_num is not None and explicit_num > 0 and explicit_num not in used:
                num = explicit_num
            else:
                while next_auto in used:
                    next_auto += 1
                num = next_auto
                next_auto += 1
            used.add(int(num))
            new_name = f"{int(num):0{width}d} - {safe_title}{_ext(rel)}"
            new_rel = new_name if not dir_part else f"{dir_part}/{new_name}"
            preview[rel] = new_rel
        return preview

    def _id3_majority_vote(self, root: RootName, audio_files: list[str]) -> dict[str, Any] | None:
        if not audio_files:
            return None

        norm = self._id3_majority.normalization

        def _norm(v: str | None) -> str | None:
            if v is None:
                return None
            s = v
            if norm.strip:
                s = s.strip()
            if norm.collapse_whitespace:
                s = " ".join(s.split())
            if norm.casefold:
                s = s.casefold()
            return s or None

        counts: dict[str, dict[str, int]] = {"author": {}, "album": {}, "title": {}}
        raw_best: dict[tuple[str, str], str] = {}

        for rel in audio_files:
            if _ext(rel) != ".mp3":
                continue
            tags = _id3v2_text_frames(self._read_id3v2_prefix(root, rel))
            author = _opt_str(tags.get("TPE2")) or _opt_str(tags.get("TPE1"))
            album = _opt_str(tags.get("TALB"))
            title = _opt_str(tags.get("TIT2"))
            for field, val in ("author", author), ("album", album), ("title", title):
                n = _norm(val)
                if not n:
                    continue
                d = counts[field]
                d[n] = int(d.get(n, 0)) + 1
                key = (field, n)
                # Keep a deterministic representative raw string.
                prev = raw_best.get(key)
                if prev is None or (val is not None and str(val) < prev):
                    raw_best[key] = str(val)

        def _majority(field: str) -> str | None:
            d = counts[field]
            if not d:
                return None
            # Deterministic tie-break: higher count, then normalized text.
            best_norm = sorted(d.items(), key=lambda it: (-int(it[1]), str(it[0])))[0][0]
            return raw_best.get((field, best_norm))

        res = {
            "author": _majority("author"),
            "album": _majority("album"),
            "title": _majority("title"),
        }
        if not any(res.values()):
            return None
        return res

    def _lookup_best_effort(self, id3_majority: dict[str, Any] | None) -> dict[str, Any] | None:
        # Best-effort integration point. Fail-safe by contract.
        if not id3_majority:
            return None
        author = _opt_str(id3_majority.get("author"))
        title = _opt_str(id3_majority.get("album")) or _opt_str(id3_majority.get("title"))
        if not author and not title:
            return None
        try:
            from plugins.metadata_sync.plugin import MetadataSync

            plugin = MetadataSync(config={"verbosity": 0})
            md = plugin.fetch_from_googlebooks(
                author=author, title=title
            ) or plugin.fetch_from_openlibrary(author=author, title=title)
            if md is None:
                return None
            # Stable dict shape.
            d = {
                "title": md.title,
                "author": md.author,
                "year": md.year,
                "publisher": md.publisher,
                "isbn": md.isbn,
                "description": md.description,
                "cover_url": md.cover_url,
                "source": md.source,
            }
            return {k: v for k, v in d.items() if v is not None}
        except Exception:
            return None

    def _find_cover_candidates(self, root: RootName, book_rel: str) -> list[str]:
        entries = self._fs.list_dir(root, book_rel, recursive=True)
        files = [e.rel_path for e in entries if not e.is_dir]
        imgs = []
        for rel in files:
            ext = _ext(rel)
            if ext in _IMG_EXT:
                imgs.append(rel)
        return sorted(imgs)


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


def _id3v2_synchsafe_to_int(b4: bytes) -> int:
    """Decode a 4-byte synchsafe integer used by ID3v2 headers."""

    if len(b4) != 4:
        return 0
    out = 0
    for b in b4:
        out = (out << 7) | (b & 0x7F)
    return int(out)


def _id3v2_text_frames(tag: bytes) -> dict[str, str]:
    """Parse a minimal subset of ID3v2 text frames.

    Supported frames: TIT2, TALB, TPE1, TPE2, TRCK.
    """

    if len(tag) < 10 or tag[:3] != b"ID3":
        return {}
    size = _id3v2_synchsafe_to_int(tag[6:10])
    data = tag[10 : 10 + size]
    out: dict[str, str] = {}

    i = 0
    while i + 10 <= len(data):
        fid = data[i : i + 4]
        if fid == b"\x00\x00\x00\x00":
            break
        frame_id = fid.decode("ascii", errors="ignore")
        frame_size = int.from_bytes(data[i + 4 : i + 8], "big", signed=False)
        # flags = data[i+8:i+10]  (ignored)
        i += 10
        if frame_size <= 0 or i + frame_size > len(data):
            break

        payload = data[i : i + frame_size]
        i += frame_size

        if frame_id not in {"TIT2", "TALB", "TPE1", "TPE2", "TRCK"}:
            continue
        if not payload:
            continue

        enc = payload[0]
        raw = payload[1:]
        txt = _decode_id3_text(enc, raw)
        if txt:
            out[frame_id] = txt

    return out


def _decode_id3_text(enc: int, data: bytes) -> str:
    """Decode ID3v2 text payload deterministically."""

    if not data:
        return ""
    # 0: latin1, 1: utf-16 (with BOM), 2: utf-16be, 3: utf-8
    codec = "latin1"
    if enc == 1:
        codec = "utf-16"
    elif enc == 2:
        codec = "utf-16-be"
    elif enc == 3:
        codec = "utf-8"
    try:
        s = data.decode(codec, errors="replace")
    except Exception:
        s = data.decode("latin1", errors="replace")
    # ID3 text fields may contain nulls or multiple values separated by null.
    s = s.replace("\x00", " ")
    return " ".join(s.split())


def _id3v2_apic_hashes(tag: bytes) -> list[str]:
    """Return SHA256 hashes for APIC payload image data."""

    if len(tag) < 10 or tag[:3] != b"ID3":
        return []
    size = _id3v2_synchsafe_to_int(tag[6:10])
    data = tag[10 : 10 + size]
    hashes: list[str] = []

    i = 0
    while i + 10 <= len(data):
        fid = data[i : i + 4]
        if fid == b"\x00\x00\x00\x00":
            break
        frame_id = fid.decode("ascii", errors="ignore")
        frame_size = int.from_bytes(data[i + 4 : i + 8], "big", signed=False)
        i += 10
        if frame_size <= 0 or i + frame_size > len(data):
            break
        payload = data[i : i + frame_size]
        i += frame_size
        if frame_id != "APIC":
            continue

        img = _extract_apic_image_bytes(payload)
        if img:
            h = hashlib.sha256()
            h.update(img)
            hashes.append(h.hexdigest())

    return sorted(set(hashes))


def _extract_apic_image_bytes(payload: bytes) -> bytes:
    """Extract embedded image bytes from an APIC frame payload."""

    if len(payload) < 5:
        return b""
    enc = payload[0]
    rest = payload[1:]
    # MIME is null-terminated latin1 string.
    nul = rest.find(b"\x00")
    if nul < 0:
        return b""
    rest = rest[nul + 1 :]
    if not rest:
        return b""
    # picture type
    rest = rest[1:]
    if not rest:
        return b""
    # description is null-terminated in selected encoding
    if enc in (0, 3):
        nul2 = rest.find(b"\x00")
        if nul2 < 0:
            return b""
        return rest[nul2 + 1 :]
    # UTF-16 variants: terminator is two null bytes
    nul2 = rest.find(b"\x00\x00")
    if nul2 < 0:
        return b""
    return rest[nul2 + 2 :]


def _parse_track_number(v: str | None) -> int | None:
    if not v:
        return None
    s = str(v).strip()
    if not s:
        return None
    # Common patterns: "1", "01", "1/10", "01/10"
    m = re.match(r"^\s*(\d{1,4})\s*(?:/\s*\d{1,4}\s*)?$", s)
    if not m:
        return None
    try:
        n = int(m.group(1))
    except Exception:
        return None
    return n if n > 0 else None


def _natural_key(s: str) -> tuple[Any, ...]:
    """Key for deterministic natural sorting."""

    parts: list[Any] = []
    for p in re.split(r"(\d+)", s.casefold()):
        if not p:
            continue
        if p.isdigit():
            parts.append(int(p))
        else:
            parts.append(p)
    return tuple(parts)


def _sanitize_filename(name: str) -> str:
    """Deterministic, filesystem-safe filename component."""

    s = str(name)
    # Replace path separators and control characters.
    s = "".join("_" if (ch in "/\\" or ord(ch) < 32) else ch for ch in s)
    s = " ".join(s.split())
    s = s.strip(" .")
    return s or "untitled"
