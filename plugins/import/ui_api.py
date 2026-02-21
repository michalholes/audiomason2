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

    from .engine import _exception_envelope

    router = APIRouter(prefix="/import/ui")

    def _status_code_for_envelope(envelope: dict[str, Any]) -> int:
        err = envelope.get("error")
        if not isinstance(err, dict):
            return 500
        code = err.get("code")
        if code == "NOT_FOUND":
            return 404
        if code in {"VALIDATION_ERROR", "INVARIANT_VIOLATION", "CONFLICTS_UNRESOLVED"}:
            return 400
        if code == "INTERNAL_ERROR":
            return 500
        return 500

    def _as_response(result: Any):
        if isinstance(result, dict) and "error" in result:
            return JSONResponse(
                status_code=_status_code_for_envelope(result),
                content=result,
            )
        return result

    def _call(handler):
        try:
            return _as_response(handler())
        except Exception as e:
            env = _exception_envelope(e)
            return JSONResponse(status_code=_status_code_for_envelope(env), content=env)

    @router.get("/flow")
    def get_flow():
        return _call(lambda: engine.get_flow_model())

    @router.get("/config")
    def get_config():
        return _call(lambda: engine.get_flow_config())

    @router.post("/config")
    def set_config(body: dict[str, Any]):
        return _call(lambda: engine.set_flow_config(body))

    @router.post("/config/reset")
    def reset_config():
        return _call(lambda: engine.reset_flow_config())

    @router.post("/session/start")
    def session_start(body: dict[str, Any]):
        def _impl():
            root = str(body.get("root") or "")
            path = str(body.get("path") or "")
            mode = str(body.get("mode") or "stage")
            return engine.create_session(root, path, mode=mode)

        return _call(_impl)

    @router.get("/session/{session_id}/state")
    def session_state(session_id: str):
        return _call(lambda: engine.get_state(session_id))

    @router.post("/session/{session_id}/step/{step_id}")
    def step_submit(session_id: str, step_id: str, body: dict[str, Any]):
        return _call(lambda: engine.submit_step(session_id, step_id, body))

    @router.post("/session/{session_id}/preview/{step_id}")
    def step_preview(session_id: str, step_id: str, body: dict[str, Any]):
        return _call(lambda: engine.preview_action(session_id, step_id, body))

    @router.post("/session/{session_id}/start_processing")
    def start_processing(session_id: str, body: dict[str, Any]):
        return _call(lambda: engine.start_processing(session_id, body))

    return router
