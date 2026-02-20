"""Core facade for the import plugin.

This module centralizes imports from audiomason.core so that other modules in
plugins.import do not directly depend on multiple external areas.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from audiomason.core.events import get_event_bus as _core_get_event_bus
from audiomason.core.jobs import JobService as _JobService

# Test seam: unit tests may monkeypatch plugins.import.core_facade.get_event_bus.
get_event_bus: Any = None


def get_bus():
    fn = get_event_bus
    if callable(fn):
        return fn()
    return _core_get_event_bus()


def get_job_service() -> _JobService:
    return _JobService()
