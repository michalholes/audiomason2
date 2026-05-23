"""OpenLibrary metadata plugin - based on AM1 openlibrary.py."""

from __future__ import annotations

import asyncio
import re
import unicodedata
from functools import partial
from typing import TypeGuard
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from audiomason.core.errors import MetadataError
from audiomason.core.serde import json_loads_object


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _as_dict_list(value: object) -> list[dict[str, object]]:
    if not _is_object_list(value):
        return []
    return [dict(item) for item in value if _is_str_object_dict(item)]


def _as_str_list(value: object) -> list[str]:
    if not _is_object_list(value):
        return []
    out: list[str] = []
    for item in value:
        text = _to_non_empty_str_or_none(item)
        if text is not None:
            out.append(text)
    return out


def _to_non_empty_str_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _to_int_or_default(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _to_int_or_none(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _to_float_or_default(value: object, default: float) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


class _CachedHttpResult:
    def __init__(self, *, max_size: int) -> None:
        self._max_size = max_size
        self._cache: dict[tuple[str, float, int], tuple[bool, str]] = {}

    def cache_clear(self) -> None:
        self._cache.clear()

    def __call__(
        self,
        *,
        url: str,
        timeout_seconds: float,
        max_response_bytes: int,
    ) -> tuple[bool, str]:
        cache_key = (url, timeout_seconds, max_response_bytes)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        req = Request(url, headers={"User-Agent": "AudioMason2/metadata_openlibrary"})
        try:
            raw_data = _read_response_bytes(
                req=req,
                timeout_seconds=timeout_seconds,
                max_response_bytes=max_response_bytes,
            )
        except HTTPError as e:
            result = (False, f"API request failed: HTTP {e.code}")
            self._store(cache_key, result)
            return result
        except URLError as e:
            result = (False, f"API request failed: {e.reason}")
            self._store(cache_key, result)
            return result
        except TimeoutError:
            result = (False, "API request failed: timeout")
            self._store(cache_key, result)
            return result
        except Exception as e:
            result = (False, f"API request failed: {e}")
            self._store(cache_key, result)
            return result

        data = raw_data
        if len(data) > max_response_bytes:
            result = (False, "API request failed: response too large")
            self._store(cache_key, result)
            return result
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as e:
            result = (False, f"Invalid API response: {e}")
            self._store(cache_key, result)
            return result
        try:
            parsed = json_loads_object(text)
        except ValueError as e:
            result = (False, f"Invalid API response: {e}")
            self._store(cache_key, result)
            return result
        if not _is_str_object_dict(parsed):
            result = (False, "Invalid API response: object expected")
            self._store(cache_key, result)
            return result

        result = (True, text)
        self._store(cache_key, result)
        return result

    def _store(self, key: tuple[str, float, int], value: tuple[bool, str]) -> None:
        self._cache[key] = value
        if len(self._cache) > self._max_size:
            oldest_key = next(iter(self._cache))
            self._cache.pop(oldest_key, None)


class OpenLibraryPlugin:
    """OpenLibrary metadata provider."""

    SEARCH_URL = "https://openlibrary.org/search.json"
    COVERS_URL = "https://covers.openlibrary.org/b/id"
    GOOGLE_BOOKS_API_URL = "https://www.googleapis.com/books/v1/volumes"

    DEFAULT_TIMEOUT_SECONDS = 1.0
    DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
    REQUEST_VERSION = 1
    JOB_VERSION = 1
    JOB_TYPE = "metadata_openlibrary.request"
    _HTTP_CACHE_MAX = 256
    _cached_http_result = _CachedHttpResult(max_size=_HTTP_CACHE_MAX)

    def __init__(self, config: dict[str, object] | None = None) -> None:
        self.config = dict(config) if config is not None else {}

        timeout = self.config.get("timeout_seconds", self.DEFAULT_TIMEOUT_SECONDS)
        max_bytes = self.config.get("max_response_bytes", self.DEFAULT_MAX_RESPONSE_BYTES)
        self.timeout_seconds = _to_float_or_default(timeout, self.DEFAULT_TIMEOUT_SECONDS)
        self.max_response_bytes = _to_int_or_default(max_bytes, self.DEFAULT_MAX_RESPONSE_BYTES)

    def build_fetch_request(self, query: dict[str, object]) -> dict[str, object]:
        payload = dict(query) if isinstance(query, dict) else {}
        return {
            "request_version": self.REQUEST_VERSION,
            "operation": "fetch",
            "payload": payload,
        }

    def build_validate_author_request(self, name: str) -> dict[str, object]:
        return {
            "request_version": self.REQUEST_VERSION,
            "operation": "validate_author",
            "payload": {"name": str(name)},
        }

    def build_validate_book_request(self, author: str, title: str) -> dict[str, object]:
        return {
            "request_version": self.REQUEST_VERSION,
            "operation": "validate_book",
            "payload": {"author": str(author), "title": str(title)},
        }

    def build_lookup_book_request(self, author: str, title: str) -> dict[str, object]:
        return {
            "request_version": self.REQUEST_VERSION,
            "operation": "lookup_book",
            "payload": {"author": str(author), "title": str(title)},
        }

    def build_phase1_validation_request(self, author: str, title: str) -> dict[str, object]:
        return {
            "request_version": self.REQUEST_VERSION,
            "operation": "phase1_validate",
            "payload": {"author": str(author), "title": str(title)},
        }

    def build_job(self, request: dict[str, object]) -> dict[str, object]:
        payload = dict(request) if isinstance(request, dict) else {}
        return {
            "job_type": self.JOB_TYPE,
            "job_version": self.JOB_VERSION,
            "provider": "metadata_openlibrary",
            "request": payload,
        }

    def build_fetch_job(self, query: dict[str, object]) -> dict[str, object]:
        return self.build_job(self.build_fetch_request(query))

    def build_validate_author_job(self, name: str) -> dict[str, object]:
        return self.build_job(self.build_validate_author_request(name))

    def build_validate_book_job(self, author: str, title: str) -> dict[str, object]:
        return self.build_job(self.build_validate_book_request(author, title))

    def build_lookup_book_job(self, author: str, title: str) -> dict[str, object]:
        return self.build_job(self.build_lookup_book_request(author, title))

    def build_phase1_validation_job(self, author: str, title: str) -> dict[str, object]:
        return self.build_job(self.build_phase1_validation_request(author, title))

    async def execute_job(self, job: dict[str, object]) -> dict[str, object]:
        return await self._execute_job(job)

    async def execute_request(self, request: dict[str, object]) -> dict[str, object]:
        return await self._execute_request(request)

    async def _execute_job(self, job: dict[str, object]) -> dict[str, object]:
        job_type = str(job.get("job_type") or "").strip()
        if job_type != self.JOB_TYPE:
            raise MetadataError(f"Unsupported job type: {job_type}")
        version = _to_int_or_default(job.get("job_version"), self.JOB_VERSION)
        if version != self.JOB_VERSION:
            raise MetadataError(f"Unsupported job version: {version}")
        request_any = job.get("request")
        request = _as_str_object_dict(request_any)
        return await self._execute_request(request)

    async def _execute_request(self, request: dict[str, object]) -> dict[str, object]:
        version = _to_int_or_default(request.get("request_version"), self.REQUEST_VERSION)
        if version != self.REQUEST_VERSION:
            raise MetadataError(f"Unsupported request version: {version}")
        operation = str(request.get("operation") or "").strip()
        payload_any = request.get("payload")
        payload = _as_str_object_dict(payload_any)

        if operation == "fetch":
            return await self._execute_fetch(payload)
        if operation == "validate_author":
            return await self._execute_validate_author(str(payload.get("name") or ""))
        if operation == "validate_book":
            return await self._execute_validate_book(
                author=str(payload.get("author") or ""),
                title=str(payload.get("title") or ""),
            )
        if operation == "lookup_book":
            return await self._execute_lookup_book(
                author=str(payload.get("author") or ""),
                title=str(payload.get("title") or ""),
            )
        if operation == "phase1_validate":
            author = str(payload.get("author") or "")
            title = str(payload.get("title") or "")
            author_validation = await self._execute_validate_author(author)
            validated_author = str(
                author_validation.get("canonical") or author_validation.get("suggestion") or author
            )
            book_validation = await self._execute_validate_book(
                author=validated_author,
                title=title,
            )
            return {
                "provider": "metadata_openlibrary",
                "author": author_validation,
                "book": book_validation,
            }
        raise MetadataError(f"Unsupported operation: {operation}")

    async def _execute_fetch(self, query: dict[str, object]) -> dict[str, object]:
        author = str(query.get("author") or "")
        title = str(query.get("title") or "")
        isbn = _to_non_empty_str_or_none(query.get("isbn"))
        docs = await self._search_docs(author=author, title=title, isbn=isbn, limit=20)
        if not docs:
            raise MetadataError("No results found")
        if isbn:
            return self._extract_metadata(docs[0])
        match = self._best_book_match(author=author, title=title, docs=docs)
        if match is None:
            raise MetadataError("No results found")
        return self._extract_metadata(match[0])

    async def _execute_validate_author(self, name: str) -> dict[str, object]:
        if not self._normalize_text(name):
            raise MetadataError("Need author name")
        docs = await self._search_docs(author=name, limit=20)
        candidate = self._best_author_name(name=name, docs=docs)
        if candidate is None:
            return {"valid": False, "canonical": None, "suggestion": None}
        if self._same_text(name, candidate):
            return {"valid": True, "canonical": candidate, "suggestion": None}
        return {"valid": False, "canonical": None, "suggestion": candidate}

    async def _execute_validate_book(self, *, author: str, title: str) -> dict[str, object]:
        if not self._normalize_text(author) and not self._normalize_text(title):
            raise MetadataError("Need author or title")
        docs = await self._search_docs(author=author, title=title, limit=20)
        match = self._best_book_match(author=author, title=title, docs=docs)

        author_candidate = author.strip()
        title_candidate = title.strip()
        if match is not None:
            doc, author_name = match
            author_candidate = author_name
            title_candidate = str(doc.get("title") or "").strip()
            canonical = {"author": author_candidate, "title": title_candidate}
            if self._same_text(author, canonical["author"]) and self._same_text(
                title,
                canonical["title"],
            ):
                return {"valid": True, "canonical": canonical, "suggestion": None}

        googlebooks_title = await self._best_googlebooks_title(
            author=author_candidate or author,
            title=title,
        )
        if googlebooks_title and not self._same_text(title, googlebooks_title):
            title_candidate = googlebooks_title

        suggestion = self._build_book_suggestion(
            author=author,
            title=title,
            author_candidate=author_candidate,
            title_candidate=title_candidate,
        )
        return {"valid": False, "canonical": None, "suggestion": suggestion}

    async def _execute_lookup_book(self, *, author: str, title: str) -> dict[str, object]:
        if not self._normalize_text(author) and not self._normalize_text(title):
            raise MetadataError("Need author or title")
        docs = await self._search_docs(author=author, title=title, limit=20)
        match = self._best_book_match(author=author, title=title, docs=docs)
        if match is None:
            raise MetadataError("No results found")
        return self._extract_metadata(match[0])

    async def _search_docs(
        self,
        *,
        author: str = "",
        title: str = "",
        isbn: str | None = None,
        limit: int = 1,
    ) -> list[dict[str, object]]:
        params: list[str] = []
        if author:
            params.append(f"author={quote_plus(author)}")
        if title:
            params.append(f"title={quote_plus(title)}")
        if isbn:
            params.append(f"isbn={isbn}")
        if not params:
            raise MetadataError("Need at least author, title, or ISBN")
        data = await self._api_request(f"{self.SEARCH_URL}?{'&'.join(params)}&limit={limit}")
        docs = data.get("docs")
        return _as_dict_list(docs)

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text)
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized.casefold())
        return " ".join(normalized.split())

    def _same_text(self, left: str, right: str) -> bool:
        return self._normalize_text(left) == self._normalize_text(right)

    def _candidate_rank(self, query_norm: str, candidate: str) -> tuple[int, int, str, str]:
        candidate_norm = self._normalize_text(candidate)
        shared = len(set(query_norm.split()) & set(candidate_norm.split()))
        return (self._match_rank(query_norm, candidate_norm), -shared, candidate_norm, candidate)

    def _best_author_name(self, *, name: str, docs: list[dict[str, object]]) -> str | None:
        query_norm = self._normalize_text(name)
        best: tuple[tuple[int, int, str, str], str] | None = None
        for doc in docs:
            raw_authors = doc.get("author_name")
            if not isinstance(raw_authors, list):
                continue
            for raw_name in raw_authors:
                candidate = str(raw_name or "").strip()
                if not self._normalize_text(candidate):
                    continue
                rank = self._candidate_rank(query_norm, candidate)
                if best is None or rank < best[0]:
                    best = (rank, candidate)
        return None if best is None else best[1]

    def _best_book_match(
        self,
        *,
        author: str,
        title: str,
        docs: list[dict[str, object]],
    ) -> tuple[dict[str, object], str] | None:
        author_norm = self._normalize_text(author)
        title_norm = self._normalize_text(title)
        best: tuple[tuple[object, ...], dict[str, object], str] | None = None
        for doc in docs:
            title_value = str(doc.get("title") or "").strip()
            if not self._normalize_text(title_value):
                continue
            authors = [
                candidate
                for candidate in _as_str_list(doc.get("author_name"))
                if self._normalize_text(candidate)
            ]
            if not authors:
                continue

            def _rank_candidate(candidate: str) -> tuple[int, int, str, str]:
                return self._candidate_rank(author_norm, candidate)

            author_name = min(
                authors,
                key=_rank_candidate,
            )
            title_rank = self._candidate_rank(title_norm, title_value)
            author_rank = self._candidate_rank(author_norm, author_name)
            rank = (
                title_rank[0],
                title_rank[1],
                author_rank[0],
                author_rank[1],
                title_rank[2],
                author_rank[2],
                str(doc.get("key") or ""),
            )
            if best is None or rank < best[0]:
                best = (rank, doc, author_name)
        return None if best is None else (best[1], best[2])

    @staticmethod
    def _match_rank(query_norm: str, candidate_norm: str) -> int:
        if not query_norm or query_norm == candidate_norm:
            return 0
        if candidate_norm.startswith(query_norm) or query_norm.startswith(candidate_norm):
            return 1
        if query_norm in candidate_norm or candidate_norm in query_norm:
            return 2
        return 3

    def _build_book_suggestion(
        self,
        *,
        author: str,
        title: str,
        author_candidate: str,
        title_candidate: str,
    ) -> dict[str, str] | None:
        author_value = author.strip()
        title_value = title.strip()
        author_changed = self._normalize_text(author_candidate) and not self._same_text(
            author_value,
            author_candidate,
        )
        title_changed = self._normalize_text(title_candidate) and not self._same_text(
            title_value,
            title_candidate,
        )
        if not author_changed and not title_changed:
            return None
        return {
            "author": author_candidate if author_changed else author_value,
            "title": title_candidate if title_changed else title_value,
        }

    async def _best_googlebooks_title(self, *, author: str, title: str) -> str | None:
        if not self._normalize_text(title):
            return None
        items = await self._search_googlebooks_items(author=author, title=title, limit=20)
        if not items:
            return None
        match = self._best_googlebooks_match(author=author, title=title, items=items)
        return None if match is None else match[1]

    async def _search_googlebooks_items(
        self,
        *,
        author: str = "",
        title: str = "",
        limit: int = 1,
    ) -> list[dict[str, object]]:
        query_parts: list[str] = []
        if author:
            query_parts.append(f"inauthor:{author}")
        if title:
            query_parts.append(f"intitle:{title}")
        if not query_parts:
            return []
        data = await self._googlebooks_request(
            query="+".join(query_parts),
            limit=limit,
        )
        items = data.get("items")
        return _as_dict_list(items)

    async def _googlebooks_request(self, *, query: str, limit: int) -> dict[str, object]:
        url = f"{self.GOOGLE_BOOKS_API_URL}?q={quote_plus(query)}&maxResults={limit}"
        return await asyncio.to_thread(
            partial(
                self._http_get_json,
                url=url,
                timeout_seconds=self.timeout_seconds,
                max_response_bytes=self.max_response_bytes,
            )
        )

    def _best_googlebooks_match(
        self,
        *,
        author: str,
        title: str,
        items: list[dict[str, object]],
    ) -> tuple[str | None, str] | None:
        author_norm = self._normalize_text(author)
        title_norm = self._normalize_text(title)
        best: tuple[tuple[object, ...], str | None, str] | None = None
        for item in items:
            volume_info = item.get("volumeInfo")
            if not _is_str_object_dict(volume_info):
                continue
            title_value = str(volume_info.get("title") or "").strip()
            if not self._normalize_text(title_value):
                continue
            authors = [
                candidate
                for candidate in _as_str_list(volume_info.get("authors"))
                if self._normalize_text(candidate)
            ]

            def _rank_candidate(candidate: str) -> tuple[int, int, str, str]:
                return self._candidate_rank(author_norm, candidate)

            author_name = (
                min(
                    authors,
                    key=_rank_candidate,
                )
                if authors
                else None
            )
            title_rank = self._candidate_rank(title_norm, title_value)
            author_rank = (
                self._candidate_rank(author_norm, author_name)
                if author_name is not None
                else (4, 0, "", "")
            )
            rank = (
                title_rank[0],
                title_rank[1],
                author_rank[0],
                author_rank[1],
                title_rank[2],
                author_rank[2],
                str(item.get("id") or ""),
            )
            if best is None or rank < best[0]:
                best = (rank, author_name, title_value)
        return None if best is None else (best[1], best[2])

    @classmethod
    def _extract_metadata(cls, doc: dict[str, object]) -> dict[str, object]:
        authors = _as_str_list(doc.get("author_name"))
        publishers = _as_str_list(doc.get("publisher"))
        isbns = _as_str_list(doc.get("isbn"))
        languages = _as_str_list(doc.get("language"))
        subjects = _as_str_list(doc.get("subject"))
        metadata: dict[str, object] = {
            "title": _to_non_empty_str_or_none(doc.get("title")),
            "subtitle": _to_non_empty_str_or_none(doc.get("subtitle")),
            "authors": authors,
            "author": ", ".join(authors) if authors else None,
            "year": _to_int_or_none(doc.get("first_publish_year")),
            "publisher": publishers[0] if publishers else None,
            "isbn": isbns[0] if isbns else None,
            "language": languages[0] if languages else None,
            "cover_url": cls._get_cover_url(_to_int_or_none(doc.get("cover_i"))),
            "subjects": subjects,
            "ebook_access": _to_non_empty_str_or_none(doc.get("ebook_access")),
        }
        return {key: value for key, value in metadata.items() if value is not None}

    async def _api_request(self, url: str) -> dict[str, object]:
        return await asyncio.to_thread(
            partial(
                self._http_get_json,
                url=url,
                timeout_seconds=self.timeout_seconds,
                max_response_bytes=self.max_response_bytes,
            )
        )

    @staticmethod
    def _http_get_json(
        *, url: str, timeout_seconds: float, max_response_bytes: int
    ) -> dict[str, object]:
        ok, payload = OpenLibraryPlugin._cached_http_result(
            url=url,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
        )
        if not ok:
            raise MetadataError(payload)
        parsed = json_loads_object(payload)
        if not _is_str_object_dict(parsed):
            raise MetadataError("Invalid API response: object expected")
        return parsed

    @classmethod
    def _get_cover_url(cls, cover_id: int | None) -> str | None:
        if not cover_id:
            return None
        return f"{cls.COVERS_URL}/{cover_id}-L.jpg"


def _read_response_bytes(*, req: Request, timeout_seconds: float, max_response_bytes: int) -> bytes:
    with urlopen(req, timeout=timeout_seconds) as resp:  # type: ignore[misc]
        raw_payload: object = resp.read(max_response_bytes + 1)  # type: ignore[misc]
    if not isinstance(raw_payload, bytes):
        raise MetadataError("API request failed: invalid response payload")
    return raw_payload
