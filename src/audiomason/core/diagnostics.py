"""Runtime diagnostics envelope + JSONL sink.

This module provides:
- A canonical envelope schema for diagnostic events.
- A central JSONL sink that can be enabled/disabled via ConfigResolver.

The sink is always registered (once per process) and self-filters when disabled.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from audiomason.core.config import ConfigError, ConfigResolver
from audiomason.core.events import get_event_bus
from audiomason.core.logging import get_logger

_logger = get_logger(__name__)


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def build_envelope(
    *,
    event: str,
    component: str,
    operation: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Build the canonical diagnostics envelope.

    Schema:
        {
          "event": "<string>",
          "component": "<string>",
          "operation": "<string>",
          "timestamp": "<iso8601 utc>",
          "data": { ... }
        }

    Timestamp is emitted in UTC with a trailing 'Z'.
    """
    ts = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {
        "event": event,
        "component": component,
        "operation": operation,
        "timestamp": ts,
        "data": data,
    }


def is_diagnostics_enabled(resolver: ConfigResolver) -> bool:
    """Return whether diagnostics are enabled.

    Canonical key:
        diagnostics.enabled

    Default:
        False

    ConfigResolver priority applies automatically (CLI -> ENV -> config -> defaults).
    Environment values are returned as strings and normalized here.
    """
    try:
        value, src = resolver.resolve("diagnostics.enabled")
    except ConfigError:
        return False

    if isinstance(value, bool):
        return value

    if value is None:
        return False

    if isinstance(value, (int, float)):
        return bool(value)

    s = str(value).strip().lower()
    if s in _TRUE_VALUES:
        return True
    if s in _FALSE_VALUES:
        return False

    if src == "env":
        _logger.warning(
            f"Invalid AUDIOMASON_DIAGNOSTICS_ENABLED value; treating as disabled. value={value!r}"
        )

    return False


def _is_envelope(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False

    required = {"event", "component", "operation", "timestamp", "data"}
    if set(obj.keys()) != required:
        return False

    if not all(
        isinstance(obj.get(k), str) for k in ("event", "component", "operation", "timestamp")
    ):
        return False

    data = obj.get("data")
    return isinstance(data, dict)


_SINK_INSTALLED = False


def install_jsonl_sink(*, resolver: ConfigResolver) -> None:
    """Install the JSONL diagnostics sink subscriber.

    This function is idempotent and registers exactly once per process.

    Sink path:
        <stage_dir>/diagnostics/diagnostics.jsonl

    When diagnostics are disabled, the subscriber performs no file IO.
    """
    global _SINK_INSTALLED
    if _SINK_INSTALLED:
        return

    def _on_any_event(event: str, data: dict[str, Any]) -> None:
        if not is_diagnostics_enabled(resolver):
            return

        try:
            stage_dir, _src = resolver.resolve("stage_dir")
        except ConfigError:
            _logger.warning("Missing stage_dir; cannot write diagnostics JSONL.")
            return
        out_path = Path(str(stage_dir)) / "diagnostics" / "diagnostics.jsonl"

        payload: dict[str, Any]
        if _is_envelope(data):
            payload = data
        else:
            payload = build_envelope(
                event=event,
                component="unknown",
                operation="unknown",
                data=data,
            )

        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(
                payload,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            with out_path.open("a", encoding="utf-8") as f:
                f.write(line)
                f.write("\n")
        except Exception as e:
            _logger.warning(f"Diagnostics sink write failed: {type(e).__name__}: {e}")

    get_event_bus().subscribe_all(_on_any_event)
    _SINK_INSTALLED = True
