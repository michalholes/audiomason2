"""Google Books metadata plugin - based on AM1 googlebooks.py."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import TypeGuard, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from audiomason.core.errors import MetadataError
from audiomason.core.serde import json_loads_object


class GoogleBooksPlugin:
    """Google Books metadata provider."""

    API_URL = "https://www.googleapis.com/books/v1/volumes"

    DEFAULT_TIMEOUT_SECONDS = 10.0
    DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024

    def __init__(self, config: dict[str, object] | None = None) -> None:
        """Initialize plugin.

        Args:
            config: Plugin configuration
        """
        self.config = dict(config) if config is not None else {}
        api_key_any = self.config.get("api_key")
        self.api_key = api_key_any if isinstance(api_key_any, str) and api_key_any else None

        timeout = self.config.get("timeout_seconds", self.DEFAULT_TIMEOUT_SECONDS)
        max_bytes = self.config.get("max_response_bytes", self.DEFAULT_MAX_RESPONSE_BYTES)
        self.timeout_seconds = _to_float_or_default(timeout, self.DEFAULT_TIMEOUT_SECONDS)
        self.max_response_bytes = _to_int_or_default(max_bytes, self.DEFAULT_MAX_RESPONSE_BYTES)

    async def fetch(self, query: dict[str, object]) -> dict[str, object]:
        """Fetch metadata from Google Books.

        Args:
            query: Query dict with keys:
                - author: Book author
                - title: Book title
                - isbn: ISBN (optional)

        Returns:
            Dict with metadata:
                - title: Book title
                - author: Book author
                - year: Publication year
                - publisher: Publisher
                - description: Description
                - isbn: ISBN
                - cover_url: Cover image URL
                - language: Language code
        """
        author = _to_str(query.get("author"))
        title = _to_str(query.get("title"))
        isbn_any = query.get("isbn")
        isbn = _to_str(isbn_any) if isbn_any is not None else ""

        if not author and not title and not isbn:
            raise MetadataError("Need at least author, title, or ISBN")

        # Build search query
        if isbn:
            search_query = f"isbn:{isbn}"
        else:
            parts: list[str] = []
            if author:
                parts.append(f"inauthor:{author}")
            if title:
                parts.append(f"intitle:{title}")
            search_query = "+".join(parts)

        # Fetch from API
        data = await self._api_request(search_query)

        # Parse response
        items = _as_dict_list(data.get("items"))
        if not items:
            raise MetadataError("No results found")

        # Get first result
        item = items[0]
        volume_info = _as_str_object_dict(item.get("volumeInfo"))
        authors = _as_str_list(volume_info.get("authors"))
        categories = _as_str_list(volume_info.get("categories"))
        industry_identifiers = _as_dict_list(volume_info.get("industryIdentifiers"))
        image_links = _as_str_object_dict(volume_info.get("imageLinks"))

        # Extract metadata
        metadata: dict[str, object] = {
            "title": _to_non_empty_str_or_none(volume_info.get("title")),
            "subtitle": _to_non_empty_str_or_none(volume_info.get("subtitle")),
            "authors": authors,
            "author": ", ".join(authors) if authors else None,
            "year": self._extract_year(_to_non_empty_str_or_none(volume_info.get("publishedDate"))),
            "publisher": _to_non_empty_str_or_none(volume_info.get("publisher")),
            "description": _to_non_empty_str_or_none(volume_info.get("description")),
            "isbn": self._extract_isbn(industry_identifiers),
            "language": _to_non_empty_str_or_none(volume_info.get("language")),
            "page_count": _to_int_or_none(volume_info.get("pageCount")),
            "categories": categories,
            "cover_url": self._get_cover_url(image_links),
        }

        # Remove None values
        metadata = {key: value for key, value in metadata.items() if value is not None}

        return metadata

    async def _api_request(self, query: str) -> dict[str, object]:
        """Make API request.

        Args:
            query: Search query

        Returns:
            API response dict
        """
        url = f"{self.API_URL}?q={quote_plus(query)}"

        if self.api_key:
            url += f"&key={self.api_key}"

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
        req = Request(url, headers={"User-Agent": "AudioMason2/metadata_googlebooks"})

        try:
            data = _read_response_bytes(
                req=req,
                timeout_seconds=timeout_seconds,
                max_response_bytes=max_response_bytes,
            )
        except HTTPError as e:
            raise MetadataError(f"API request failed: HTTP {e.code}") from e
        except URLError as e:
            raise MetadataError(f"API request failed: {e.reason}") from e
        except TimeoutError as e:
            raise MetadataError("API request failed: timeout") from e
        except Exception as e:
            raise MetadataError(f"API request failed: {e}") from e

        if len(data) > max_response_bytes:
            raise MetadataError("API request failed: response too large")

        try:
            payload = json_loads_object(data.decode("utf-8"))
        except ValueError as e:
            raise MetadataError(f"Invalid API response: {e}") from e
        if not _is_str_object_dict(payload):
            raise MetadataError("Invalid API response: object expected")
        return payload

    def _extract_year(self, date_str: str | None) -> int | None:
        """Extract year from date string.

        Args:
            date_str: Date string (YYYY-MM-DD or YYYY)

        Returns:
            Year as integer or None
        """
        if not date_str:
            return None

        try:
            # Try to extract YYYY from beginning
            year_str = date_str.split("-")[0]
            return int(year_str)
        except (ValueError, IndexError):
            return None

    def _extract_isbn(self, identifiers: list[dict[str, object]]) -> str | None:
        """Extract ISBN from identifiers.

        Args:
            identifiers: List of industry identifiers

        Returns:
            ISBN string or None
        """
        if not identifiers:
            return None

        # Prefer ISBN_13 over ISBN_10
        for identifier in identifiers:
            if identifier.get("type") == "ISBN_13":
                value = _to_non_empty_str_or_none(identifier.get("identifier"))
                if value is not None:
                    return value

        for identifier in identifiers:
            if identifier.get("type") == "ISBN_10":
                value = _to_non_empty_str_or_none(identifier.get("identifier"))
                if value is not None:
                    return value

        return None

    def _get_cover_url(self, image_links: dict[str, object]) -> str | None:
        """Get best cover URL from image links.

        Args:
            image_links: Image links dict

        Returns:
            Cover URL or None
        """
        if not image_links:
            return None

        # Prefer larger images
        for size in ["extraLarge", "large", "medium", "small", "thumbnail", "smallThumbnail"]:
            if size in image_links:
                url = _to_non_empty_str_or_none(image_links.get(size))
                if url is None:
                    continue
                # Use HTTPS
                if url.startswith("http://"):
                    url = "https://" + url[7:]
                return url

        return None


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


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


def _to_str(value: object) -> str:
    return value if isinstance(value, str) else ""


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


def _read_response_bytes(*, req: Request, timeout_seconds: float, max_response_bytes: int) -> bytes:
    with urlopen(req, timeout=timeout_seconds) as resp:  # type: ignore[misc]
        raw_payload: object = resp.read(max_response_bytes + 1)  # type: ignore[misc]
    if not isinstance(raw_payload, bytes):
        raise MetadataError("API request failed: invalid response payload")
    return raw_payload
