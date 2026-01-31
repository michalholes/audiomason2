"""Google Books metadata plugin - based on AM1 googlebooks.py."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import quote_plus

from audiomason.core.errors import MetadataError


class GoogleBooksPlugin:
    """Google Books metadata provider."""

    API_URL = "https://www.googleapis.com/books/v1/volumes"

    def __init__(self, config: dict | None = None) -> None:
        """Initialize plugin.

        Args:
            config: Plugin configuration
        """
        self.config = config or {}
        self.api_key = self.config.get("api_key")

    async def fetch(self, query: dict[str, Any]) -> dict[str, Any]:
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
        author = query.get("author", "")
        title = query.get("title", "")
        isbn = query.get("isbn")

        if not author and not title and not isbn:
            raise MetadataError("Need at least author, title, or ISBN")

        # Build search query
        if isbn:
            search_query = f"isbn:{isbn}"
        else:
            parts = []
            if author:
                parts.append(f"inauthor:{author}")
            if title:
                parts.append(f"intitle:{title}")
            search_query = "+".join(parts)

        # Fetch from API
        data = await self._api_request(search_query)

        # Parse response
        if not data or "items" not in data or not data["items"]:
            raise MetadataError("No results found")

        # Get first result
        item = data["items"][0]
        volume_info = item.get("volumeInfo", {})

        # Extract metadata
        metadata = {
            "title": volume_info.get("title"),
            "subtitle": volume_info.get("subtitle"),
            "authors": volume_info.get("authors", []),
            "author": ", ".join(volume_info.get("authors", [])),
            "year": self._extract_year(volume_info.get("publishedDate")),
            "publisher": volume_info.get("publisher"),
            "description": volume_info.get("description"),
            "isbn": self._extract_isbn(volume_info.get("industryIdentifiers", [])),
            "language": volume_info.get("language"),
            "page_count": volume_info.get("pageCount"),
            "categories": volume_info.get("categories", []),
            "cover_url": self._get_cover_url(volume_info.get("imageLinks", {})),
        }

        # Remove None values
        metadata = {k: v for k, v in metadata.items() if v is not None}

        return metadata

    async def _api_request(self, query: str) -> dict[str, Any]:
        """Make API request.

        Args:
            query: Search query

        Returns:
            API response dict
        """
        url = f"{self.API_URL}?q={quote_plus(query)}"

        if self.api_key:
            url += f"&key={self.api_key}"

        # Use curl (no network access, but structure is ready)
        cmd = ["curl", "-s", url]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                raise MetadataError("API request failed")

            data = json.loads(stdout.decode())
            return data

        except json.JSONDecodeError as e:
            raise MetadataError(f"Invalid API response: {e}") from e
        except Exception as e:
            raise MetadataError(f"API request failed: {e}") from e

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

    def _extract_isbn(self, identifiers: list[dict]) -> str | None:
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
                return identifier.get("identifier")

        for identifier in identifiers:
            if identifier.get("type") == "ISBN_10":
                return identifier.get("identifier")

        return None

    def _get_cover_url(self, image_links: dict) -> str | None:
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
                url = image_links[size]
                # Use HTTPS
                if url.startswith("http://"):
                    url = "https://" + url[7:]
                return url

        return None
