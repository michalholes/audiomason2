"""UI-facing FastAPI router for the import plugin.

The host is responsible for mounting this router.

ASCII-only.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol, TypeGuard, cast

from plugins.file_io.service import FileService


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


class _UiEngine(Protocol):
    _fs: FileService

    def get_file_service(self) -> FileService: ...

    def get_flow_model(self) -> dict[str, object]: ...

    def get_state(self, session_id: str) -> dict[str, object]: ...

    def get_step_definition(self, session_id: str, step_id: str) -> dict[str, object]: ...

    def submit_step(
        self, session_id: str, step_id: str, body: dict[str, object]
    ) -> dict[str, object]: ...

    def preview_action(
        self, session_id: str, step_id: str, body: dict[str, object]
    ) -> dict[str, object]: ...

    def start_processing(self, session_id: str, body: dict[str, object]) -> dict[str, object]: ...


class _RouteRegistrar(Protocol):
    def add_api_route(self, path: str, endpoint: object, *, methods: list[str]) -> object: ...


class _JsonResponseFactory(Protocol):
    def __call__(self, *, status_code: int, content: dict[str, object]) -> object: ...


class _HtmlResponseFactory(Protocol):
    def __call__(self, content: str) -> object: ...


class _FileResponseFactory(Protocol):
    def __call__(self, path: str) -> object: ...


def build_router(*, engine: object):
    try:
        from fastapi import APIRouter
        from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
    except Exception as e:  # pragma: no cover
        raise RuntimeError("fastapi is required for import UI router") from e

    from .engine import ImportWizardEngine
    from .engine_diagnostics_required import start_process_runtime
    from .engine_session_start_boundary import ALLOWED_USER_START_INTENTS, start_user_facing_session
    from .engine_util import exception_envelope
    from .field_schema_validation import FieldSchemaValidationError
    from .session_effective_model import EffectiveModelJsonError
    from .ui_editor_api import bind_editor_routes

    engine_api = cast(_UiEngine, engine)
    engine_start = cast(ImportWizardEngine, engine)

    start_process_runtime(engine=engine_api)
    router = APIRouter(prefix="/import/ui")
    route_registrar = cast(_RouteRegistrar, router)
    json_response = cast(_JsonResponseFactory, JSONResponse)
    html_response = cast(_HtmlResponseFactory, HTMLResponse)
    file_response = cast(_FileResponseFactory, FileResponse)

    base_dir = Path(__file__).resolve().parent
    ui_web_dir = base_dir / "ui" / "web"
    assets_dir = ui_web_dir / "assets"

    def ui_asset(asset_path: str) -> object:
        if not assets_dir.is_dir():
            return json_response(status_code=404, content={"error": {"code": "NOT_FOUND"}})

        rel = Path(asset_path)
        if rel.is_absolute() or ".." in rel.parts:
            return json_response(status_code=404, content={"error": {"code": "NOT_FOUND"}})

        root = assets_dir.resolve()
        candidate = (assets_dir / rel).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return json_response(status_code=404, content={"error": {"code": "NOT_FOUND"}})

        if not candidate.is_file():
            return json_response(status_code=404, content={"error": {"code": "NOT_FOUND"}})

        return file_response(str(candidate))

    session_start_allowed_keys = {"intent", "mode", "path", "root"}
    session_start_required_keys = {"mode", "path", "root"}
    session_start_allowed_modes = {"inplace", "stage"}

    def _validate_session_start_body(body: object) -> tuple[str, str, str, str | None]:
        if not _is_str_object_dict(body):
            raise FieldSchemaValidationError(
                message="request body must be an object",
                path="$",
                reason="invalid_type",
                meta={},
            )

        payload = dict(body)

        keys = set(payload)
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

        root = payload.get("root")
        if not isinstance(root, str) or not root:
            raise FieldSchemaValidationError(
                message="root must be a non-empty string",
                path="$.root",
                reason="missing_or_invalid",
                meta={},
            )

        path = payload.get("path")
        if not isinstance(path, str) or not path:
            raise FieldSchemaValidationError(
                message="path must be a non-empty string",
                path="$.path",
                reason="missing_or_invalid",
                meta={},
            )

        mode = payload.get("mode")
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

        intent = payload.get("intent")
        if intent is not None:
            if not isinstance(intent, str) or not intent:
                raise FieldSchemaValidationError(
                    message="intent must be a non-empty string when provided",
                    path="$.intent",
                    reason="missing_or_invalid",
                    meta={"allowed": sorted(ALLOWED_USER_START_INTENTS)},
                )
            if intent not in ALLOWED_USER_START_INTENTS:
                raise FieldSchemaValidationError(
                    message="intent must be one of the allowed values",
                    path="$.intent",
                    reason="invalid_enum",
                    meta={"allowed": sorted(ALLOWED_USER_START_INTENTS), "value": intent},
                )

        return root, path, mode, intent

    def _status_code_for_envelope(envelope: dict[str, object]) -> int:
        err = envelope.get("error")
        if not _is_str_object_dict(err):
            return 500
        code = err.get("code")
        if code == "NOT_FOUND":
            return 404
        if code == "SESSION_START_CONFLICT":
            return 409
        if code in {"VALIDATION_ERROR", "INVARIANT_VIOLATION", "CONFLICTS_UNRESOLVED"}:
            return 400
        if code == "INTERNAL_ERROR":
            return 500
        return 500

    def _as_response(result: object) -> object:
        if _is_str_object_dict(result) and "error" in result:
            return json_response(
                status_code=_status_code_for_envelope(result),
                content=result,
            )
        return result

    def _effective_model_reason(message: str) -> str:
        if "missing" in message:
            return "missing_file"
        if "invalid JSON" in message:
            return "invalid_json"
        if "must be an object" in message:
            return "invalid_type"
        return "invalid"

    def _call(handler: Callable[[], object]) -> object:
        try:
            return _as_response(handler())
        except EffectiveModelJsonError as e:
            env: dict[str, object] = {
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": str(e),
                    "details": [
                        {
                            "path": "$.effective_model",
                            "reason": _effective_model_reason(str(e)),
                            "meta": {"path": str(e.rel_path)},
                        }
                    ],
                }
            }
            return json_response(status_code=400, content=env)
        except Exception as e:
            env_error = exception_envelope(e)
            return json_response(
                status_code=_status_code_for_envelope(env_error),
                content=env_error,
            )

    def ui_index() -> object:
        idx = ui_web_dir / "index.html"
        if not idx.is_file():
            env: dict[str, object] = {
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
            return json_response(status_code=404, content=env)
        return html_response(idx.read_text(encoding="utf-8"))

    def get_flow() -> object:
        return _call(lambda: engine_api.get_flow_model())

    bind_editor_routes(router=router, engine=engine_api, call=_call)

    def session_start(body: dict[str, object]) -> object:
        def _impl() -> dict[str, object]:
            root, path, mode, intent = _validate_session_start_body(body)
            return start_user_facing_session(
                engine=engine_start,
                root=root,
                relative_path=path,
                mode=mode,
                intent=intent,
            )

        return _call(_impl)

    def session_state(session_id: str) -> object:
        return _call(lambda: engine_api.get_state(session_id))

    def step_definition(session_id: str, step_id: str) -> object:
        return _call(lambda: engine_api.get_step_definition(session_id, step_id))

    def step_submit(session_id: str, step_id: str, body: dict[str, object]) -> object:
        return _call(lambda: engine_api.submit_step(session_id, step_id, body))

    def step_preview(session_id: str, step_id: str, body: dict[str, object]) -> object:
        return _call(lambda: engine_api.preview_action(session_id, step_id, body))

    def start_processing(session_id: str, body: dict[str, object]) -> object:
        return _call(lambda: engine_api.start_processing(session_id, body))

    route_registrar.add_api_route("/assets/{asset_path:path}", ui_asset, methods=["GET"])
    route_registrar.add_api_route("/", ui_index, methods=["GET"])
    route_registrar.add_api_route("/flow", get_flow, methods=["GET"])
    route_registrar.add_api_route("/session/start", session_start, methods=["POST"])
    route_registrar.add_api_route("/session/{session_id}/state", session_state, methods=["GET"])
    route_registrar.add_api_route(
        "/session/{session_id}/step/{step_id}",
        step_definition,
        methods=["GET"],
    )
    route_registrar.add_api_route(
        "/session/{session_id}/step/{step_id}",
        step_submit,
        methods=["POST"],
    )
    route_registrar.add_api_route(
        "/session/{session_id}/preview/{step_id}",
        step_preview,
        methods=["POST"],
    )
    route_registrar.add_api_route(
        "/session/{session_id}/start_processing",
        start_processing,
        methods=["POST"],
    )

    return router
