from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI, HTTPException, Request

from audiomason.core.config_service import ConfigService
from audiomason.core.errors import ConfigError
from audiomason.core.serde import yaml_safe_load_text

from ..util.web_observability import web_operation


def _dict_str_object(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    out: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(key, str):
            out[key] = item
    return out


def _parse_effective_snapshot(yaml_text: str) -> dict[str, object]:
    try:
        data = yaml_safe_load_text(yaml_text)
    except Exception:
        return {}
    return _dict_str_object(data)


def _parse_key_path(body: dict[str, object]) -> str:
    key_path = body.get("key_path")
    if not isinstance(key_path, str) or not key_path.strip():
        raise HTTPException(status_code=400, detail="key_path is required")
    return key_path


def _ascii_detail(text: str) -> str:
    """Return ASCII-only text safe for HTTP error bodies."""

    return (text or "").encode("ascii", "backslashreplace").decode("ascii")


def mount_am_config(app: FastAPI) -> None:
    """Config endpoints.

    Web UI must not edit raw YAML configuration text.
    """

    svc = ConfigService()

    def get_am_config(request: Request) -> dict[str, object]:
        with web_operation(request, name="am.config.get", ctx={}):
            snapshot_yaml = svc.get_effective_config_snapshot()
            out: dict[str, object] = {
                "config": svc.get_config(),
                "effective_snapshot": _parse_effective_snapshot(snapshot_yaml),
                "effective_snapshot_yaml": snapshot_yaml,
            }
            return out

    def set_am_config_value(body: dict[str, object]) -> dict[str, object]:
        key_path = _parse_key_path(body)
        value = body.get("value")
        try:
            svc.set_value(key_path, value)
        except ConfigError as e:
            raise HTTPException(status_code=400, detail=_ascii_detail(str(e))) from e
        return {"ok": True}

    def unset_am_config_value(body: dict[str, object]) -> dict[str, object]:
        key_path = _parse_key_path(body)
        try:
            svc.unset_value(key_path)
        except ConfigError as e:
            raise HTTPException(status_code=400, detail=_ascii_detail(str(e))) from e
        return {"ok": True}

    app.add_api_route("/api/am/config", get_am_config, methods=["GET"])
    app.add_api_route("/api/am/config/set", set_am_config_value, methods=["POST"])
    app.add_api_route("/api/am/config/unset", unset_am_config_value, methods=["POST"])
