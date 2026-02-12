"""Core LogBus (EventBus-style) for publishing log records.

This module provides a minimal publish/subscribe mechanism for the core logger.
It is fail-safe: subscriber exceptions must never crash publishing.

Note: LogBus is a log streaming mechanism only. It is NOT a replacement for the
authoritative runtime diagnostics emission entry point.
"""

from __future__ import annotations

import contextlib
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class LogRecord:
    level_name: str
    plain: str
    logger_name: str


class LogBus:
    def __init__(self) -> None:
        self._subs_by_level: dict[str, list[Callable[[LogRecord], None]]] = {}
        self._subs_all: list[Callable[[LogRecord], None]] = []

    def subscribe(self, level_name: str, cb: Callable[[LogRecord], None]) -> None:
        self._subs_by_level.setdefault(level_name, []).append(cb)

    def unsubscribe(self, level_name: str, cb: Callable[[LogRecord], None]) -> None:
        subs = self._subs_by_level.get(level_name)
        if not subs:
            return
        try:
            subs.remove(cb)
        except ValueError:
            return
        if not subs:
            self._subs_by_level.pop(level_name, None)

    def subscribe_all(self, cb: Callable[[LogRecord], None]) -> None:
        self._subs_all.append(cb)

    def unsubscribe_all(self, cb: Callable[[LogRecord], None]) -> None:
        try:
            self._subs_all.remove(cb)
        except ValueError:
            return

    def publish(self, record: LogRecord) -> None:
        for cb in list(self._subs_all):
            self._invoke_cb(cb, record)

        for cb in list(self._subs_by_level.get(record.level_name, [])):
            self._invoke_cb(cb, record)

    def clear(self) -> None:
        self._subs_by_level.clear()
        self._subs_all.clear()

    def _invoke_cb(self, cb: Callable[[LogRecord], None], record: LogRecord) -> None:
        try:
            cb(record)
        except Exception:
            # Fail-safe: never call core logger here (avoid recursion).
            msg = "LogBus subscriber raised; suppressed.\n" + traceback.format_exc()
            with contextlib.suppress(Exception):
                sys.stderr.write(msg)


_LOG_BUS: LogBus | None = None


def get_log_bus() -> LogBus:
    global _LOG_BUS
    if _LOG_BUS is None:
        _LOG_BUS = LogBus()
    return _LOG_BUS
