"""Generic interfaces for plugins.

All plugins implement one or more of these interfaces.
These are intentionally generic to allow maximum flexibility.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from audiomason.core.context import ProcessingContext


class IProcessor(Protocol):
    """Process media through pipeline.

    This is the main workhorse interface. Processors transform
    the context by doing actual work (converting audio, writing tags, etc).

    CRITICAL: Must be non-interactive! No user prompts allowed.
    All decisions must be in context already.
    """

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        """Process context and return updated context.

        Args:
            context: Current processing context with all decisions made

        Returns:
            Updated context with processing results

        Raises:
            PluginError: If processing fails
        """
        ...


class IProvider(Protocol):
    """Provide external data (metadata, covers, etc).

    Providers fetch data from external sources like APIs, databases,
    or web scraping.

    Examples:
    - Google Books API metadata
    - OpenLibrary API metadata
    - Cover image downloads
    - Transcription services
    """

    async def fetch(self, query: dict[str, Any]) -> dict[str, Any]:
        """Fetch data based on query.

        Args:
            query: Query parameters (flexible dict for different providers)

        Returns:
            Fetched data (flexible dict, provider-specific)

        Raises:
            PluginError: If fetch fails
        """
        ...


class IUI(Protocol):
    """User interface.

    UI plugins handle ALL user interaction. This includes:
    - Collecting metadata in PHASE 1 (interactive)
    - Displaying progress in PHASE 2 (read-only)
    - Error reporting
    - Results display

    Examples:
    - CLI (Typer-based terminal interface)
    - Web UI (browser interface)
    - API server (REST/GraphQL)
    - Daemon (background service)
    """

    async def run(self) -> None:
        """Run the user interface.

        This is the main entry point for UI plugins.
        The UI is responsible for:
        1. Collecting user input (PHASE 1)
        2. Starting processing
        3. Showing progress (PHASE 2)
        4. Displaying results

        Raises:
            PluginError: If UI fails
        """
        ...


class IStorage(Protocol):
    """Storage backend.

    Storage plugins handle reading and writing data to various backends.

    Examples:
    - Local filesystem
    - S3/cloud storage
    - Network shares
    - Cache storage
    """

    async def read(self, path: str) -> bytes:
        """Read data from storage.

        Args:
            path: Path to read (backend-specific format)

        Returns:
            Raw bytes

        Raises:
            FileError: If read fails
        """
        ...

    async def write(self, path: str, data: bytes) -> None:
        """Write data to storage.

        Args:
            path: Path to write (backend-specific format)
            data: Raw bytes to write

        Raises:
            FileError: If write fails
        """
        ...


class IEnricher(Protocol):
    """Enrich context with additional data.

    Enrichers add data to the context without transforming media.
    They're typically used for:
    - Adding computed metadata
    - Enhancing existing data
    - Running analysis

    Examples:
    - AI-powered metadata enrichment
    - Genre detection
    - Language detection
    - Quality analysis
    """

    async def enrich(self, context: ProcessingContext) -> ProcessingContext:
        """Enrich context with additional data.

        Args:
            context: Current context

        Returns:
            Context with additional enrichment data

        Raises:
            PluginError: If enrichment fails
        """
        ...
