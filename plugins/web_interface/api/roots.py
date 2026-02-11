from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request

from audiomason.core.config import ConfigResolver


def _get_resolver(request: Request) -> ConfigResolver:
    resolver = getattr(request.app.state, "config_resolver", None)
    if isinstance(resolver, ConfigResolver):
        return resolver
    return ConfigResolver()


def _resolve_show_jobs_root(resolver: ConfigResolver) -> bool:
    try:
        val, _src = resolver.resolve("web_interface.browse.show_jobs_root")
    except Exception:
        return True
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        return bool(val)
    if isinstance(val, str):
        return val.strip().lower() not in {"0", "false", "no", "off", ""}
    return True


def mount_roots(app: FastAPI) -> None:
    @app.get("/api/roots")
    def list_roots(request: Request) -> dict[str, Any]:
        resolver = _get_resolver(request)
        show_jobs = _resolve_show_jobs_root(resolver)

        items: list[dict[str, str]] = [
            {"id": "inbox", "label": "Inbox"},
            {"id": "stage", "label": "Stage"},
        ]
        if show_jobs:
            items.append({"id": "jobs", "label": "Jobs"})
        items.append({"id": "outbox", "label": "Outbox"})

        return {"items": items}
