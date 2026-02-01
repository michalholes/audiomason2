from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..util.paths import am_config_path


class PutConfig(BaseModel):
    yaml: str


def mount_am_config(app: FastAPI) -> None:
    @app.get("/api/am/config")
    def get_am_config() -> dict[str, Any]:
        path = am_config_path()
        if not path.exists():
            return {"path": str(path), "yaml": ""}
        return {"path": str(path), "yaml": path.read_text(encoding="utf-8")}

    @app.put("/api/am/config")
    def put_am_config(body: PutConfig) -> dict[str, Any]:
        path = am_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body.yaml, encoding="utf-8")
        return {"ok": True, "path": str(path)}
