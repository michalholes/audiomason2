"""Synchronous Metadata Plugin - fetch from Google Books and OpenLibrary."""

from __future__ import annotations

import contextlib
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass

from audiomason.core import ProcessingContext
from audiomason.core.errors import AudioMasonError


class MetadataError(AudioMasonError):
    """Metadata fetching error."""

    pass


@dataclass
class BookMetadata:
    """Book metadata from online sources."""

    title: str | None = None
    author: str | None = None
    year: int | None = None
    publisher: str | None = None
    isbn: str | None = None
    description: str | None = None
    cover_url: str | None = None
    source: str | None = None


class MetadataSync:
    """Synchronous metadata fetcher.

    Supports:
    - Google Books API
    - OpenLibrary API
    """

    GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"
    OPENLIBRARY_API = "https://openlibrary.org/search.json"

    def __init__(self, config: dict | None = None) -> None:
        """Initialize plugin.

        Args:
            config: Plugin configuration
        """
        self.config = config or {}
        self.verbosity = self.config.get("verbosity", 1)
        self.timeout = self.config.get("timeout", 10)
        self.providers = self.config.get("providers", ["googlebooks", "openlibrary"])

    def _log_debug(self, msg: str) -> None:
        """Log debug message (verbosity >= 3)."""
        if self.verbosity >= 3:
            print(f"[DEBUG] [metadata_sync] {msg}")

    def _log_verbose(self, msg: str) -> None:
        """Log verbose message (verbosity >= 2)."""
        if self.verbosity >= 2:
            print(f"[VERBOSE] [metadata_sync] {msg}")

    def _log_info(self, msg: str) -> None:
        """Log info message (verbosity >= 1)."""
        if self.verbosity >= 1:
            print(f"[metadata_sync] {msg}")

    def _log_error(self, msg: str) -> None:
        """Log error message (always shown)."""
        print(f"[ERROR] [metadata_sync] {msg}")

    def fetch_from_googlebooks(
        self, author: str | None = None, title: str | None = None
    ) -> BookMetadata | None:
        """Fetch metadata from Google Books API.

        Args:
            author: Author name
            title: Book title

        Returns:
            BookMetadata or None
        """
        if not author and not title:
            self._log_verbose("No search criteria for Google Books")
            return None

        # Build search query
        query_parts = []
        if author:
            query_parts.append(f'inauthor:"{author}"')
        if title:
            query_parts.append(f'intitle:"{title}"')

        query = " ".join(query_parts)

        self._log_info(f"Searching Google Books: {query}")

        # Build URL
        params = {"q": query, "maxResults": 1, "printType": "books"}

        url = f"{self.GOOGLE_BOOKS_API}?{urllib.parse.urlencode(params)}"
        self._log_debug(f"URL: {url}")

        try:
            # Make request
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))

            # Parse response
            if data.get("totalItems", 0) == 0:
                self._log_verbose("No results from Google Books")
                return None

            item = data["items"][0]
            volume_info = item.get("volumeInfo", {})

            metadata = BookMetadata(
                title=volume_info.get("title"),
                author=", ".join(volume_info.get("authors", [])) or None,
                publisher=volume_info.get("publisher"),
                description=volume_info.get("description"),
                source="googlebooks",
            )

            # Extract year
            published_date = volume_info.get("publishedDate")
            if published_date:
                with contextlib.suppress(ValueError, IndexError):
                    metadata.year = int(published_date[:4])

            # Extract ISBN
            for identifier in volume_info.get("industryIdentifiers", []):
                if identifier.get("type") in ["ISBN_13", "ISBN_10"]:
                    metadata.isbn = identifier.get("identifier")
                    break

            # Extract cover URL
            image_links = volume_info.get("imageLinks", {})
            metadata.cover_url = (
                image_links.get("large")
                or image_links.get("medium")
                or image_links.get("thumbnail")
            )

            self._log_verbose(f"Found: {metadata.title} by {metadata.author}")
            return metadata

        except urllib.error.URLError as e:
            self._log_verbose(f"Google Books request failed: {e}")
            return None
        except json.JSONDecodeError as e:
            self._log_verbose(f"Failed to parse Google Books response: {e}")
            return None
        except Exception as e:
            self._log_verbose(f"Google Books error: {e}")
            return None

    def fetch_from_openlibrary(
        self, author: str | None = None, title: str | None = None
    ) -> BookMetadata | None:
        """Fetch metadata from OpenLibrary API.

        Args:
            author: Author name
            title: Book title

        Returns:
            BookMetadata or None
        """
        if not author and not title:
            self._log_verbose("No search criteria for OpenLibrary")
            return None

        self._log_info(f"Searching OpenLibrary: {author} - {title}")

        # Build query parameters
        params = {}
        if author:
            params["author"] = author
        if title:
            params["title"] = title
        params["limit"] = "1"

        url = f"{self.OPENLIBRARY_API}?{urllib.parse.urlencode(params)}"
        self._log_debug(f"URL: {url}")

        try:
            # Make request
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))

            # Parse response
            if data.get("numFound", 0) == 0:
                self._log_verbose("No results from OpenLibrary")
                return None

            doc = data["docs"][0]

            metadata = BookMetadata(
                title=doc.get("title"),
                author=", ".join(doc.get("author_name", [])) or None,
                publisher=", ".join(doc.get("publisher", [])) or None,
                source="openlibrary",
            )

            # Extract year
            if "first_publish_year" in doc:
                metadata.year = doc["first_publish_year"]

            # Extract ISBN
            if "isbn" in doc and doc["isbn"]:
                metadata.isbn = doc["isbn"][0]

            # Extract cover URL
            if "cover_i" in doc:
                cover_id = doc["cover_i"]
                metadata.cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"

            self._log_verbose(f"Found: {metadata.title} by {metadata.author}")
            return metadata

        except urllib.error.URLError as e:
            self._log_verbose(f"OpenLibrary request failed: {e}")
            return None
        except json.JSONDecodeError as e:
            self._log_verbose(f"Failed to parse OpenLibrary response: {e}")
            return None
        except Exception as e:
            self._log_verbose(f"OpenLibrary error: {e}")
            return None

    def fetch_metadata(
        self, author: str | None = None, title: str | None = None
    ) -> BookMetadata | None:
        """Fetch metadata from configured providers.

        Tries providers in order until one succeeds.

        Args:
            author: Author name
            title: Book title

        Returns:
            BookMetadata or None
        """
        for provider in self.providers:
            if provider == "googlebooks":
                metadata = self.fetch_from_googlebooks(author, title)
                if metadata:
                    return metadata

            elif provider == "openlibrary":
                metadata = self.fetch_from_openlibrary(author, title)
                if metadata:
                    return metadata

        self._log_verbose("No metadata found from any provider")
        return None

    def process(self, context: ProcessingContext) -> ProcessingContext:
        """Main processing method (IProcessor interface).

        Fetches metadata and updates context.

        Args:
            context: Processing context

        Returns:
            Updated context with metadata
        """
        # Get search criteria from context
        author = getattr(context, "author", None) or getattr(context, "artist", None)
        title = getattr(context, "title", None) or getattr(context, "album", None)

        if not author and not title:
            self._log_verbose("No author/title in context, skipping metadata fetch")
            return context

        # Fetch metadata
        metadata = self.fetch_metadata(author, title)

        if metadata:
            # Update context with fetched metadata
            if metadata.title and not hasattr(context, "title"):
                context.title = metadata.title

            if metadata.author and not hasattr(context, "author"):
                context.author = metadata.author

            if metadata.year:
                context.year = metadata.year

            if metadata.publisher:
                setattr(context, "publisher", metadata.publisher)

            if metadata.isbn:
                context.isbn = metadata.isbn

            if metadata.description:
                setattr(context, "description", metadata.description)

            if metadata.cover_url:
                context.cover_url = metadata.cover_url

            self._log_info(f"Metadata updated from {metadata.source}")

        return context
