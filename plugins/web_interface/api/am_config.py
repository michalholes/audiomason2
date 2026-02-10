from __future__ import annotations

from typing import Any

import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from audiomason.core.config_service import ConfigService
from audiomason.core.errors import ConfigError

from ..util.paths import debug_enabled


class SetConfigValue(BaseModel):
    key_path: str
    value: Any


class UnsetConfigValue(BaseModel):
    key_path: str


def _parse_effective_snapshot(yaml_text: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(yaml_text)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _ascii_detail(text: str) -> str:
    """Return ASCII-only text safe for HTTP error bodies."""

    return (text or "").encode("ascii", "backslashreplace").decode("ascii")


def mount_am_config(app: FastAPI) -> None:
    """Config endpoints.

    Web UI must not edit raw YAML configuration text.
    """

    svc = ConfigService()

    @app.get("/api/am/config")
    def get_am_config() -> dict[str, Any]:
        snapshot_yaml = svc.get_effective_config_snapshot()
        out: dict[str, Any] = {
            "config": svc.get_config(),
            "effective_snapshot": _parse_effective_snapshot(snapshot_yaml),
        }
        if debug_enabled():
            out["path"] = str(svc.user_config_path)
        return out

    @app.post("/api/am/config/set")
    def set_am_config_value(body: SetConfigValue) -> dict[str, Any]:
        try:
            svc.set_value(body.key_path, body.value)
        except ConfigError as e:
            raise HTTPException(status_code=400, detail=_ascii_detail(str(e))) from e
        return {"ok": True}

    @app.post("/api/am/config/unset")
    def unset_am_config_value(body: UnsetConfigValue) -> dict[str, Any]:
        try:
            svc.unset_value(body.key_path)
        except ConfigError as e:
            raise HTTPException(status_code=400, detail=_ascii_detail(str(e))) from e
        return {"ok": True}
