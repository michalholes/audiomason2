"""Event bus for plugin communication.

Simple pub/sub system allowing plugins to communicate
without direct dependencies.
"""

from __future__ import annotations

import traceback
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from audiomason.core.logging import get_logger

_logger = get_logger(__name__)


class EventBus:
    """Simple event bus for plugin communication.

    Example:
        bus = EventBus()

        # Subscribe
        from audiomason.core.logging import get_logger
        log = get_logger("example")

        def on_file_processed(data):
            log.info(f"File processed: {data['path']}")

        bus.subscribe("file_processed", on_file_processed)

        # Publish
        bus.publish("file_processed", {"path": "/tmp/book.mp3"})
    """

    def __init__(self) -> None:
        """Initialize event bus."""
        self._subscribers: dict[str, list[Callable[[dict[str, Any]], None]]] = defaultdict(list)
        self._all_subscribers: list[Callable[[str, dict[str, Any]], None]] = []

    def subscribe(self, event: str, callback: Callable[[dict[str, Any]], None]) -> None:
        """Subscribe to an event.

        Args:
            event: Event name
            callback: Callback function (receives event data dict)
        """
        self._subscribers[event].append(callback)

    def unsubscribe(self, event: str, callback: Callable[[dict[str, Any]], None]) -> None:
        """Unsubscribe from an event.

        Args:
            event: Event name
            callback: Callback function to remove
        """
        if event in self._subscribers:
            self._subscribers[event].remove(callback)

    def subscribe_all(self, callback: Callable[[str, dict[str, Any]], None]) -> None:
        """Subscribe to all published events.

        Args:
            callback: Callback function (receives event name and event data dict)
        """
        self._all_subscribers.append(callback)

    def publish(self, event: str, data: dict[str, Any] | None = None) -> None:
        """Publish an event.

        Args:
            event: Event name
            data: Event data (optional)
        """
        data = data or {}

        # Exact-event subscribers (legacy behavior).
        for cb_event in list(self._subscribers.get(event, [])):
            try:
                cb_event(data)
            except Exception as e:
                # Log error but don't crash (fail-safe diagnostics requirement).
                tb = traceback.format_exc()
                msg = (
                    f"Error in event handler for '{event}' (callback={cb_event}): "
                    f"{type(e).__name__}: {e}\n"
                    f"{tb}"
                )
                _logger.error(msg)

        # All-event subscribers (diagnostics sink, etc.).
        for cb_all in list(self._all_subscribers):
            try:
                cb_all(event, data)
            except Exception as e:
                tb = traceback.format_exc()
                msg = (
                    f"Error in all-event handler (event='{event}', callback={cb_all}): "
                    f"{type(e).__name__}: {e}\n"
                    f"{tb}"
                )
                _logger.error(msg)

    async def publish_async(self, event: str, data: dict[str, Any] | None = None) -> None:
        """Publish an event asynchronously.

        Args:
            event: Event name
            data: Event data (optional)
        """
        # For now, just call synchronous version
        # Can be enhanced later with proper async handling
        self.publish(event, data)

    def clear(self) -> None:
        """Clear all subscribers."""
        self._subscribers.clear()
        self._all_subscribers.clear()


# Global event bus instance
_global_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Get global event bus instance.

    Returns:
        Global EventBus instance
    """
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus
