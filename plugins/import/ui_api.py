"""UI-facing FastAPI router for the import plugin.

The host is responsible for mounting this router.

ASCII-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_router(*, engine: Any):
    try:
        from fastapi import APIRouter
        from fastapi.responses import HTMLResponse, JSONResponse
        from fastapi.staticfiles import StaticFiles
    except Exception as e:  # pragma: no cover
        raise RuntimeError("fastapi is required for import UI router") from e

    from .engine import _exception_envelope
    from .field_schema_validation import FieldSchemaValidationError

    router = APIRouter(prefix="/import/ui")

    base_dir = Path(__file__).resolve().parent
    ui_web_dir = base_dir / "ui" / "web"
    assets_dir = ui_web_dir / "assets"

    if assets_dir.is_dir():
        router.mount("/assets", StaticFiles(directory=str(assets_dir)), name="import-ui-assets")

    session_start_allowed_keys = {"mode", "path", "root"}
    session_start_required_keys = {"mode", "path", "root"}
    session_start_allowed_modes = {"inplace", "stage"}

    def _validate_session_start_body(body: Any) -> tuple[str, str, str]:
        if not isinstance(body, dict):
            raise FieldSchemaValidationError(
                message="request body must be an object",
                path="$",
                reason="invalid_type",
                meta={},
            )

        keys = {k for k in body if isinstance(k, str)}
        unknown = sorted(keys - session_start_allowed_keys)
        if unknown:
            key = unknown[0]
            raise FieldSchemaValidationError(
                message="unknown field in request body",
                path=f"$.{key}",
                reason="unknown_field",
                meta={
                    "allowed": sorted(session_start_allowed_keys),
                    "unknown": unknown,
                },
            )

        missing = sorted(session_start_required_keys - keys)
        if missing:
            key = missing[0]
            raise FieldSchemaValidationError(
                message="missing required field in request body",
                path=f"$.{key}",
                reason="missing_required",
                meta={"required": sorted(session_start_required_keys)},
            )

        root = body.get("root")
        if not isinstance(root, str) or not root:
            raise FieldSchemaValidationError(
                message="root must be a non-empty string",
                path="$.root",
                reason="missing_or_invalid",
                meta={},
            )

        path = body.get("path")
        if not isinstance(path, str) or not path:
            raise FieldSchemaValidationError(
                message="path must be a non-empty string",
                path="$.path",
                reason="missing_or_invalid",
                meta={},
            )

        mode = body.get("mode")
        if not isinstance(mode, str) or not mode:
            raise FieldSchemaValidationError(
                message="mode must be a non-empty string",
                path="$.mode",
                reason="missing_or_invalid",
                meta={"allowed": sorted(session_start_allowed_modes)},
            )
        if mode not in session_start_allowed_modes:
            raise FieldSchemaValidationError(
                message="mode must be one of the allowed values",
                path="$.mode",
                reason="invalid_enum",
                meta={
                    "allowed": sorted(session_start_allowed_modes),
                    "value": mode,
                },
            )

        return root, path, mode

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

    @router.get("/")
    def ui_index():
        idx = ui_web_dir / "index.html"
        if not idx.is_file():
            env = {
                "error": {
                    "code": "NOT_FOUND",
                    "message": "import UI index.html is missing",
                    "details": [
                        {
                            "path": "$.ui.web.index",
                            "reason": "not_found",
                            "meta": {"expected": str(idx)},
                        }
                    ],
                }
            }
            return JSONResponse(status_code=404, content=env)
        return HTMLResponse(idx.read_text(encoding="utf-8"))

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
            root, path, mode = _validate_session_start_body(body)
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
