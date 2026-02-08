from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from audiomason.core.config_service import ConfigService

from ..util.paths import debug_enabled


class SetConfigValue(BaseModel):
    key_path: str
    value: Any


def mount_am_config(app: FastAPI) -> None:
    """Config endpoints.

    Web UI must not edit raw YAML configuration text.
    """

    svc = ConfigService()

    @app.get("/api/am/config")
    def get_am_config() -> dict[str, Any]:
        out: dict[str, Any] = {
            "config": svc.get_config(),
            "effective_snapshot": svc.get_effective_config_snapshot(),
        }
        if debug_enabled():
            out["path"] = str(svc.user_config_path)
        return out

    @app.post("/api/am/config/set")
    def set_am_config_value(body: SetConfigValue) -> dict[str, Any]:
        svc.set_value(body.key_path, body.value)
        return {"ok": True}
