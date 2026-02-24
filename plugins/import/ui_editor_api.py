"""Import plugin: UI editor endpoints (FlowConfig + WizardDefinition).

This module binds editor routes to the import UI router.
It is kept separate from ui_api.py to reduce monolith risk.

ASCII-only.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from plugins.file_io.service import RootName

from .errors import error_envelope
from .field_schema_validation import FieldSchemaValidationError
from .flow_config_validation import normalize_flow_config
from .wizard_definition_model import (
    DEFAULT_WIZARD_DEFINITION,
    load_or_bootstrap_wizard_definition,
    validate_wizard_definition_structure,
)


def bind_editor_routes(
    *,
    router: Any,
    engine: Any,
    call: Callable[[Callable[[], Any]], Any],
) -> None:
    """Bind editor routes to router.

    call(handler) must wrap handler() into a JSONResponse with canonical
    error envelopes (see ui_api._call).
    """

    @router.get("/config")
    def get_config():
        return call(lambda: _get_flow_config(engine))

    @router.post("/config")
    def set_config(body: dict[str, Any]):
        return call(lambda: _set_flow_config(engine, body))

    @router.post("/config/validate")
    def validate_config(body: dict[str, Any]):
        return call(lambda: _validate_flow_config(engine, body))

    @router.post("/config/reset")
    def reset_config():
        return call(lambda: _reset_flow_config(engine))

    @router.get("/config/history")
    def config_history():
        return call(lambda: _flow_config_history(engine))

    @router.post("/config/rollback")
    def config_rollback(body: dict[str, Any]):
        return call(lambda: _rollback_flow_config(engine, body))

    @router.get("/wizard-definition")
    def get_wizard_definition():
        return call(lambda: _get_wizard_definition(engine))

    @router.post("/wizard-definition")
    def set_wizard_definition(body: dict[str, Any]):
        return call(lambda: _set_wizard_definition(engine, body))

    @router.post("/wizard-definition/validate")
    def validate_wizard_definition(body: dict[str, Any]):
        return call(lambda: _validate_wizard_definition(engine, body))

    @router.post("/wizard-definition/reset")
    def reset_wizard_definition():
        return call(lambda: _reset_wizard_definition(engine))

    @router.get("/wizard-definition/history")
    def wizard_definition_history():
        return call(lambda: _wizard_definition_history(engine))

    @router.post("/wizard-definition/rollback")
    def wizard_definition_rollback(body: dict[str, Any]):
        return call(lambda: _rollback_wizard_definition(engine, body))


def _validate_wrapper(
    *,
    body: Any,
    required_key: str,
    allowed_keys: set[str],
) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise FieldSchemaValidationError(
            message="request body must be an object",
            path="$",
            reason="invalid_type",
            meta={},
        )

    keys = {k for k in body if isinstance(k, str)}
    unknown = sorted(keys - allowed_keys)
    if unknown:
        key = unknown[0]
        raise FieldSchemaValidationError(
            message="unknown field in request body",
            path=f"$.{key}",
            reason="unknown_field",
            meta={
                "allowed": sorted(allowed_keys),
                "unknown": unknown,
            },
        )

    if required_key not in keys:
        raise FieldSchemaValidationError(
            message="missing required field in request body",
            path=f"$.{required_key}",
            reason="missing_required",
            meta={"required": sorted([required_key])},
        )

    return dict(body)


def _history_items(ids: list[str]) -> dict[str, Any]:
    # Timestamp is UI-only. Keep deterministic and ISO-8601.
    items: list[dict[str, Any]] = []
    for i, fid in enumerate(ids):
        sec = i % 60
        items.append(
            {
                "id": fid,
                "timestamp": f"1970-01-01T00:00:{sec:02d}Z",
            }
        )
    return {"items": items}


def _engine_fs(engine: Any):
    fs = getattr(engine, "_fs", None)
    if fs is None:
        raise RuntimeError("engine missing _fs")
    return fs


def _get_flow_config(engine: Any) -> dict[str, Any]:
    from .editor_storage import load_flow_config, reset_flow_config

    fs = _engine_fs(engine)
    if not fs.exists(RootName.WIZARDS, "import/config/flow_config.json"):
        reset_flow_config(fs)
    cfg = load_flow_config(fs)
    return {"config": normalize_flow_config(cfg)}


def _set_flow_config(engine: Any, body: Any) -> dict[str, Any]:
    from .editor_storage import save_flow_config

    obj = _validate_wrapper(body=body, required_key="config", allowed_keys={"config"})
    cfg_any = obj.get("config")
    cfg = normalize_flow_config(cfg_any)
    fs = _engine_fs(engine)
    save_flow_config(fs, cfg)
    return {"config": cfg}


def _validate_flow_config(engine: Any, body: Any) -> dict[str, Any]:
    obj = _validate_wrapper(body=body, required_key="config", allowed_keys={"config"})
    cfg = normalize_flow_config(obj.get("config"))
    return {"config": cfg}


def _reset_flow_config(engine: Any) -> dict[str, Any]:
    from .editor_storage import load_flow_config, reset_flow_config

    fs = _engine_fs(engine)
    reset_flow_config(fs)
    cfg = load_flow_config(fs)
    return {"config": normalize_flow_config(cfg)}


def _flow_config_history(engine: Any) -> dict[str, Any]:
    from .editor_storage import list_history

    fs = _engine_fs(engine)
    ids = list_history(fs, kind="flow_config")
    return _history_items(ids[:5])


def _rollback_flow_config(engine: Any, body: Any) -> dict[str, Any]:
    from .editor_storage import list_history, load_flow_config, rollback

    obj = _validate_wrapper(body=body, required_key="id", allowed_keys={"id"})
    fid = obj.get("id")
    if not isinstance(fid, str) or not fid:
        raise FieldSchemaValidationError(
            message="id must be a non-empty string",
            path="$.id",
            reason="missing_or_invalid",
            meta={},
        )

    fs = _engine_fs(engine)
    if fid not in set(list_history(fs, kind="flow_config")):
        return error_envelope(
            "NOT_FOUND",
            "not found",
            details=[{"path": "$.id", "reason": "not_found", "meta": {}}],
        )
    rollback(fs, kind="flow_config", fingerprint=fid)
    cfg = load_flow_config(fs)
    return {"config": normalize_flow_config(cfg)}


def _get_wizard_definition(engine: Any) -> dict[str, Any]:
    fs = _engine_fs(engine)
    wd = load_or_bootstrap_wizard_definition(fs)
    return {"definition": wd}


def _set_wizard_definition(engine: Any, body: Any) -> dict[str, Any]:
    from .wizard_editor_storage import save_wizard_definition_with_history

    obj = _validate_wrapper(
        body=body,
        required_key="definition",
        allowed_keys={"definition"},
    )
    wd_any = obj.get("definition")
    validate_wizard_definition_structure(wd_any)
    fs = _engine_fs(engine)
    save_wizard_definition_with_history(fs, wd_any)
    wd = load_or_bootstrap_wizard_definition(fs)
    return {"definition": wd}


def _validate_wizard_definition(engine: Any, body: Any) -> dict[str, Any]:
    obj = _validate_wrapper(
        body=body,
        required_key="definition",
        allowed_keys={"definition"},
    )
    wd_any = obj.get("definition")
    validate_wizard_definition_structure(wd_any)
    return {"definition": wd_any}


def _reset_wizard_definition(engine: Any) -> dict[str, Any]:
    from .wizard_editor_storage import reset_wizard_definition

    fs = _engine_fs(engine)
    reset_wizard_definition(fs, DEFAULT_WIZARD_DEFINITION)
    wd = load_or_bootstrap_wizard_definition(fs)
    return {"definition": wd}


def _wizard_definition_history(engine: Any) -> dict[str, Any]:
    from .wizard_editor_storage import list_wizard_definition_history

    fs = _engine_fs(engine)
    ids = list_wizard_definition_history(fs)
    return _history_items(ids[:5])


def _rollback_wizard_definition(engine: Any, body: Any) -> dict[str, Any]:
    from .wizard_editor_storage import (
        list_wizard_definition_history,
        load_wizard_definition,
        rollback_wizard_definition,
    )

    obj = _validate_wrapper(body=body, required_key="id", allowed_keys={"id"})
    fid = obj.get("id")
    if not isinstance(fid, str) or not fid:
        raise FieldSchemaValidationError(
            message="id must be a non-empty string",
            path="$.id",
            reason="missing_or_invalid",
            meta={},
        )

    fs = _engine_fs(engine)
    if fid not in set(list_wizard_definition_history(fs)):
        return error_envelope(
            "NOT_FOUND",
            "not found",
            details=[{"path": "$.id", "reason": "not_found", "meta": {}}],
        )

    rollback_wizard_definition(fs, fingerprint=fid)
    wd = load_wizard_definition(fs)
    return {"definition": wd}
