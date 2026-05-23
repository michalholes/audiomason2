"""Web interface plugin entrypoint for AudioMason plugin loader.

This module adapts the standalone WebInterfacePlugin implementation (core.py)
to the loader's expected async run() entrypoint and injected context fields.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .core import WebInterfacePlugin as _CoreWebInterface


@runtime_checkable
class _SupportsResolve(Protocol):
    def resolve(self, key: str) -> tuple[object, object]: ...


def _to_int_or_default(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _to_str_or_default(value: object, default: str) -> str:
    if isinstance(value, str) and value:
        return value
    return default


class WebInterfacePlugin:
    """Plugin-loader compatible web interface plugin."""

    def __init__(self, config: dict[str, object] | None = None) -> None:
        self.config = dict(config) if config is not None else {}
        self.config_resolver: object | None = None
        self.plugin_loader: object | None = None
        self.verbosity: int = 1

    async def run(self) -> None:
        # Prefer ConfigResolver provided by CLI plugin, if available.
        host = "0.0.0.0"
        port = 8080
        verbosity = _to_int_or_default(self.verbosity, 1)
        resolver = self.config_resolver
        if isinstance(resolver, _SupportsResolve):
            try:
                resolved_host, _source_h = resolver.resolve("web.host")
                if isinstance(resolved_host, str) and resolved_host:
                    host = resolved_host
                resolved_port, _source = resolver.resolve("web.port")
                port = _to_int_or_default(resolved_port, 8080)
            except Exception:
                port = 8080
        else:
            # Fall back to plugin config only.
            port = _to_int_or_default(self.config.get("port"), 8080)
            host = _to_str_or_default(self.config.get("host"), host)

        await _CoreWebInterface().serve(
            host=host,
            port=port,
            config_resolver=self.config_resolver,
            plugin_loader=self.plugin_loader,
            verbosity=verbosity,
        )
