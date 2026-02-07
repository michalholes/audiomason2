"""Web interface plugin entrypoint for AudioMason plugin loader.

This module adapts the standalone WebInterfacePlugin implementation (core.py)
to the loader's expected async run() entrypoint and injected context fields.
"""

from __future__ import annotations

from typing import Any

from .core import WebInterfacePlugin as _CoreWebInterface


class WebInterfacePlugin:
    """Plugin-loader compatible web interface plugin."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.config_resolver: Any | None = None
        self.plugin_loader: Any | None = None
        self.verbosity: int = 1

    async def run(self) -> None:
        # Prefer ConfigResolver provided by CLI plugin, if available.
        host = "0.0.0.0"
        port = 8080
        if self.config_resolver is not None:
            try:
                resolved_port, _source = self.config_resolver.resolve("web.port")
                port = int(resolved_port)
            except Exception:
                port = 8080
        else:
            # Fall back to plugin config only.
            try:
                port = int(self.config.get("port", 8080))
            except Exception:
                port = 8080
            host = str(self.config.get("host", host))

        await _CoreWebInterface().serve(host=host, port=port)
