"""test_all_plugin - reference plugin exercising supported interfaces.

This plugin is deterministic and non-interactive.
"""

from __future__ import annotations

from typing import Any

from audiomason.core.context import ProcessingContext


class TestAllPlugin:
    """Sample plugin implementing multiple interfaces for testing and reference."""

    async def process(self, context: ProcessingContext) -> ProcessingContext:
        """IProcessor: mark step complete and add a warning."""
        context.mark_step_complete("test_all_plugin.process")
        context.add_warning("test_all_plugin.process ran")
        return context

    async def enrich(self, context: ProcessingContext) -> ProcessingContext:
        """IEnricher: set a deterministic metadata flag."""
        context.final_metadata["test_all_plugin_enriched"] = True
        return context

    async def fetch(self, query: dict[str, Any]) -> dict[str, Any]:
        """IProvider: return a deterministic provider response."""
        return {
            "provider": "test_all_plugin",
            "query": query,
            "ok": True,
        }

    async def run(self) -> None:
        """IUI: non-interactive deterministic UI run."""
        print("test_all_plugin UI run")

    async def read(self, path: str) -> bytes:
        """IStorage stub."""
        raise NotImplementedError("test_all_plugin does not implement storage backends")

    async def write(self, path: str, data: bytes) -> None:
        """IStorage stub."""
        raise NotImplementedError("test_all_plugin does not implement storage backends")

    def get_cli_commands(self) -> dict[str, Any]:
        """ICLICommands: provide deterministic CLI command handlers."""

        def test_all(argv: list[str]) -> str:
            _ = argv
            msg = "OK:test-all"
            print(msg)
            return msg

        def test_echo(argv: list[str]) -> str:
            msg = "ECHO:" + " ".join(argv)
            print(msg)
            return msg

        return {
            "test-all": test_all,
            "test-echo": test_echo,
        }
