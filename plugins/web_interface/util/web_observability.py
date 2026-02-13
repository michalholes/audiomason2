from __future__ import annotations

import time
import traceback
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Any

from fastapi import Request

from audiomason.core.diagnostics import build_envelope
from audiomason.core.events import get_event_bus
from audiomason.core.logging import get_logger


def _ascii(text: str) -> str:
    return (text or "").encode("ascii", "backslashreplace").decode("ascii")


def _get_logger(request: Request) -> Any:
    injected = getattr(getattr(request, "app", None), "state", None)
    injected = getattr(injected, "web_logger", None)
    if injected is not None:
        return injected
    return get_logger("web_interface")


@contextmanager
def web_operation(
    request: Request,
    *,
    name: str,
    ctx: dict[str, Any] | None = None,
    component: str = "web_interface",
) -> Iterator[None]:
    """Emit diagnostics + core log records for a web internal operation.

    This is intended for call boundaries inside the web plugin (handler -> service).
    """
    if ctx is None:
        ctx = {}

    logger = _get_logger(request)
    t0 = time.monotonic()

    start_env = build_envelope(
        event="operation.start",
        component=component,
        operation=name,
        data=ctx,
    )
    with suppress(Exception):
        get_event_bus().publish("operation.start", start_env)

    with suppress(Exception):
        logger.info(_ascii(f"{name}: start {ctx}"))

    try:
        yield
    except Exception as e:
        dur_ms = int((time.monotonic() - t0) * 1000)
        tb = traceback.format_exc()
        fail_ctx = dict(ctx)
        fail_ctx.update(
            {
                "status": "failed",
                "duration_ms": dur_ms,
                "error_type": type(e).__name__,
                "error": str(e),
                "traceback": tb,
            }
        )
        fail_env = build_envelope(
            event="operation.end",
            component=component,
            operation=name,
            data=fail_ctx,
        )
        with suppress(Exception):
            get_event_bus().publish("operation.end", fail_env)

        with suppress(Exception):
            logger.error(_ascii(f"{name}: failed {fail_ctx}"))
        raise

    dur_ms = int((time.monotonic() - t0) * 1000)
    end_ctx = dict(ctx)
    end_ctx.update({"status": "succeeded", "duration_ms": dur_ms})
    end_env = build_envelope(
        event="operation.end",
        component=component,
        operation=name,
        data=end_ctx,
    )
    with suppress(Exception):
        get_event_bus().publish("operation.end", end_env)

    with suppress(Exception):
        logger.info(_ascii(f"{name}: end {end_ctx}"))
