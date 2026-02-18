"""UI-facing FastAPI router for the import plugin.

The host is responsible for mounting this router.

ASCII-only.
"""

from __future__ import annotations

from typing import Any


def build_router(*, engine: Any):
    try:
        from fastapi import APIRouter
        from fastapi.responses import JSONResponse
    except Exception as e:  # pragma: no cover
        raise RuntimeError("fastapi is required for import UI router") from e

    router = APIRouter(prefix="/import/ui")

    @router.get("/flow")
    def get_flow():
        return engine.get_flow_model()

    @router.get("/config")
    def get_config():
        fs = engine.get_file_service()
        from plugins.file_io.service import RootName

        from .defaults import ensure_default_models
        from .storage import read_json

        ensure_default_models(fs)
        return read_json(fs, RootName.WIZARDS, "import/config/flow_config.json")

    @router.post("/config")
    def set_config(body: dict[str, Any]):
        validated = engine.validate_flow_config(body)
        if validated.get("ok") is not True:
            return JSONResponse(status_code=400, content=validated)
        normalized = engine._normalize_flow_config(body)
        fs = engine.get_file_service()
        from plugins.file_io.service import RootName

        from .storage import atomic_write_json

        atomic_write_json(fs, RootName.WIZARDS, "import/config/flow_config.json", normalized)
        return normalized

    @router.post("/config/reset")
    def reset_config():
        default_cfg = {"version": 1, "steps": {}, "defaults": {}, "ui": {}}
        fs = engine.get_file_service()
        from plugins.file_io.service import RootName

        from .storage import atomic_write_json

        atomic_write_json(fs, RootName.WIZARDS, "import/config/flow_config.json", default_cfg)
        return default_cfg

    @router.post("/session/start")
    def session_start(body: dict[str, Any]):
        root = str(body.get("root") or "")
        path = str(body.get("path") or "")
        mode = str(body.get("mode") or "stage")
        return engine.create_session(root, path, mode=mode)

    @router.get("/session/{session_id}/state")
    def session_state(session_id: str):
        return engine.get_state(session_id)

    @router.post("/session/{session_id}/step/{step_id}")
    def step_submit(session_id: str, step_id: str, body: dict[str, Any]):
        return engine.submit_step(session_id, step_id, body)

    @router.post("/session/{session_id}/start_processing")
    def start_processing(session_id: str, body: dict[str, Any]):
        return engine.start_processing(session_id, body)

    return router
