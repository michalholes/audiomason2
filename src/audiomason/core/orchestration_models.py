"""Models used by the core orchestration layer.

These models are intentionally UI-agnostic so they can be used by CLI and the
future web interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from audiomason.core.context import ProcessingContext


def _new_job_meta() -> dict[str, str]:
    return {}


class PluginLoaderProtocol(Protocol):
    def get_plugin(self, name: str) -> object: ...


class ProcessContractEntryPoint(Protocol):
    def __call__(
        self,
        *,
        job_id: str,
        job_meta: dict[str, str],
        plugin_loader: PluginLoaderProtocol,
    ) -> object: ...


@dataclass(frozen=True)
class ProcessRequest:
    contexts: list[ProcessingContext]
    pipeline_path: Path
    plugin_loader: PluginLoaderProtocol


@dataclass(frozen=True)
class ProcessContractRequest:
    contract_id: str
    plugin_name: str
    entrypoint_name: str
    plugin_loader: PluginLoaderProtocol
    job_meta: dict[str, str] = field(default_factory=_new_job_meta)
