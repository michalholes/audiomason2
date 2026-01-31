"""OpenLibrary metadata plugin - based on AM1 openlibrary.py."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import quote_plus

from audiomason.core.errors import MetadataError


class OpenLibraryPlugin:
    """OpenLibrary metadata provider."""

    SEARCH_URL = "https://openlibrary.org/search.json"
    COVERS_URL = "https://covers.openlibrary.org/b/id"

    def __init__(self, config: dict | None = None) -> None:
        """Initialize plugin.

        Args:
            config: Plugin configuration
        """
        self.config = config or {}

    async def fetch(self, query: dict[str, Any]) -> dict[str, Any]:
        """Fetch metadata from OpenLibrary.

        Args:
            query: Query dict with keys:
                - author: Book author
                - title: Book title
                - isbn: ISBN (optional)

        Returns:
            Dict with metadata
        """
        author = query.get("author", "")
        title = query.get("title", "")
        isbn = query.get("isbn")

        if not author and not title and not isbn:
            raise MetadataError("Need at least author, title, or ISBN")

        # Build search query
        params = []
        if author:
            params.append(f"author={quote_plus(author)}")
        if title:
            params.append(f"title={quote_plus(title)}")
        if isbn:
            params.append(f"isbn={isbn}")

        url = f"{self.SEARCH_URL}?{'&'.join(params)}&limit=1"

        # Fetch from API
        data = await self._api_request(url)

        # Parse response
        if not data or "docs" not in data or not data["docs"]:
            raise MetadataError("No results found")

        # Get first result
        doc = data["docs"][0]

        # Extract metadata
        metadata = {
            "title": doc.get("title"),
            "subtitle": doc.get("subtitle"),
            "authors": doc.get("author_name", []),
            "author": ", ".join(doc.get("author_name", [])),
            "year": doc.get("first_publish_year"),
            "publisher": doc.get("publisher", [None])[0] if doc.get("publisher") else None,
            "isbn": doc.get("isbn", [None])[0] if doc.get("isbn") else None,
            "language": doc.get("language", [None])[0] if doc.get("language") else None,
            "cover_url": self._get_cover_url(doc.get("cover_i")),
            "subjects": doc.get("subject", []),
            "ebook_access": doc.get("ebook_access"),
        }

        # Remove None values
        metadata = {k: v for k, v in metadata.items() if v is not None}

        return metadata

    async def _api_request(self, url: str) -> dict[str, Any]:
        """Make API request.

        Args:
            url: Request URL

        Returns:
            API response dict
        """
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

    def _get_cover_url(self, cover_id: int | None) -> str | None:
        """Get cover URL from cover ID.

        Args:
            cover_id: OpenLibrary cover ID

        Returns:
            Cover URL or None
        """
        if not cover_id:
            return None

        # Return large cover
        return f"{self.COVERS_URL}/{cover_id}-L.jpg"
