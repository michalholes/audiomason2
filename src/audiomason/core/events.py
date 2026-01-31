"""Event bus for plugin communication.

Simple pub/sub system allowing plugins to communicate
without direct dependencies.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable


class EventBus:
    """Simple event bus for plugin communication.

    Example:
        bus = EventBus()

        # Subscribe
        def on_file_processed(data):
            print(f"File processed: {data['path']}")

        bus.subscribe("file_processed", on_file_processed)

        # Publish
        bus.publish("file_processed", {"path": "/tmp/book.mp3"})
    """

    def __init__(self) -> None:
        """Initialize event bus."""
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)

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

    def publish(self, event: str, data: dict[str, Any] | None = None) -> None:
        """Publish an event.

        Args:
            event: Event name
            data: Event data (optional)
        """
        data = data or {}

        for callback in self._subscribers.get(event, []):
            try:
                callback(data)
            except Exception as e:
                # Log error but don't crash
                # TODO: Use proper logging
                print(f"Error in event handler for '{event}': {e}")

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
