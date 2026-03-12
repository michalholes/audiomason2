"""Import plugin: UI editor endpoints (FlowConfig + WizardDefinition).

This module binds editor routes to the import UI router.
It is kept separate from ui_api.py to reduce monolith risk.

ASCII-only.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .errors import FinalizeError, error_envelope
from .field_schema_validation import FieldSchemaValidationError
from .flow_config_validation import normalize_flow_config

try:
    from .flow_config_validation import validate_flow_config_editor_boundary
except ImportError:  # compatibility with issue-131 baseline

    def validate_flow_config_editor_boundary(raw: Any) -> dict[str, Any]:
        return normalize_flow_config(raw)


from .wizard_definition_model import (
    canonicalize_wizard_definition,
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

    @router.post("/config/activate")
    def activate_config():
        return call(lambda: _activate_flow_config(engine))

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

    @router.post("/wizard-definition/activate")
    def activate_wizard_definition():
        return call(lambda: _activate_wizard_definition(engine))

    @router.get("/wizard-definition/history")
    def wizard_definition_history():
        return call(lambda: _wizard_definition_history(engine))

    @router.post("/wizard-definition/rollback")
    def wizard_definition_rollback(body: dict[str, Any]):
        return call(lambda: _rollback_wizard_definition(engine, body))

    @router.get("/primitive-registry")
    def get_primitive_registry():
        return call(lambda: _get_primitive_registry(engine))

    @router.get("/steps-index")
    def get_steps_index():
        return call(lambda: _get_steps_index(engine))

    @router.get("/steps/{step_id}")
    def get_step_details(step_id: str):
        return call(lambda: _get_step_details(engine, step_id))

    @router.get("/transition-condition-prefixes")
    def get_transition_condition_prefixes():
        return call(lambda: _get_transition_condition_prefixes())


_TRANSITION_CONDITION_PREFIXES: tuple[str, ...] = (
    "cfg.defaults.",
    "session.",
    "wizard.",
)


def _ensure_ascii_step_id(step_id: Any) -> str:
    if not isinstance(step_id, str) or not step_id:
        raise FieldSchemaValidationError(
            message="step_id must be a non-empty string",
            path="$.step_id",
            reason="missing_or_invalid",
            meta={},
        )
    try:
        step_id.encode("ascii")
    except UnicodeEncodeError as err:
        raise FieldSchemaValidationError(
            message="step_id must be ASCII",
            path="$.step_id",
            reason="invalid_ascii",
            meta={},
        ) from err
    return step_id


def _classify_step(step_id: str) -> tuple[str, str]:
    from .flow_runtime import CONDITIONAL_STEP_IDS, MANDATORY_STEP_IDS, OPTIONAL_STEP_IDS

    if step_id in CONDITIONAL_STEP_IDS:
        kind = "conditional"
    elif step_id in MANDATORY_STEP_IDS:
        kind = "mandatory"
    elif step_id in OPTIONAL_STEP_IDS:
        kind = "optional"
    else:
        kind = "optional"

    if step_id == "select_authors":
        pinned = "first"
    elif step_id == "processing":
        pinned = "last"
    else:
        pinned = "none"

    return kind, pinned


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


def _validate_editor_condition_shape(cond: Any, *, path: str) -> None:
    if cond is None or isinstance(cond, bool):
        return
    if not isinstance(cond, dict):
        raise FieldSchemaValidationError(
            message="transition condition must be an object, bool, or null",
            path=path,
            reason="invalid_type",
            meta={},
        )

    op_any = cond.get("op")
    if op_any is None:
        if "path" in cond and ("equals" in cond or "not_equals" in cond):
            return
        raise FieldSchemaValidationError(
            message="unsupported transition operator",
            path=path,
            reason="unsupported_operator",
            meta={},
        )

    if not isinstance(op_any, str) or not op_any:
        raise FieldSchemaValidationError(
            message="transition operator must be a non-empty string",
            path=f"{path}.op",
            reason="missing_or_invalid",
            meta={},
        )

    if op_any in {"eq", "ne", "exists", "truthy"}:
        return
    if op_any in {"and", "or"}:
        conds = cond.get("conds")
        if not isinstance(conds, list):
            raise FieldSchemaValidationError(
                message="boolean transition operator requires conds[]",
                path=f"{path}.conds",
                reason="missing_required",
                meta={"operator": op_any},
            )
        for index, item in enumerate(conds):
            _validate_editor_condition_shape(item, path=f"{path}.conds[{index}]")
        return
    if op_any == "not":
        _validate_editor_condition_shape(cond.get("cond"), path=f"{path}.cond")
        return

    raise FieldSchemaValidationError(
        message="unsupported transition operator",
        path=f"{path}.op",
        reason="unsupported_operator",
        meta={"operator": op_any},
    )


def _validate_v2_editor_only_rules(definition: Any) -> None:
    if not isinstance(definition, dict) or definition.get("version") != 2:
        return
    graph = definition.get("graph")
    edges = graph.get("edges") if isinstance(graph, dict) else None
    if not isinstance(edges, list):
        return
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            continue
        _validate_editor_condition_shape(
            edge.get("when"),
            path=f"$.definition.graph.edges[{index}].when",
        )


def _translate_v2_definition_error(err: FinalizeError) -> FieldSchemaValidationError:
    message = str(err)
    if message == "select_authors must be the first step":
        return FieldSchemaValidationError(
            message=message,
            path="$.definition.graph.nodes[0].step_id",
            reason="pinned_first",
            meta={"step_id": "select_authors", "position": 0},
        )
    if message == "wizard_definition processing must be the terminal step":
        return FieldSchemaValidationError(
            message=message,
            path="$.definition.graph.nodes",
            reason="pinned_last",
            meta={"step_id": "processing"},
        )
    if message.startswith("INVALID_CONDITION_PATH: "):
        path_part = message.split(": ", 1)[1].split(" ", 1)[0]
        return FieldSchemaValidationError(
            message=message,
            path="$.definition" + path_part[1:],
            reason="unsupported_operator",
            meta={},
        )
    if message.startswith("MISSING_PRIORITY: "):
        return FieldSchemaValidationError(
            message=message,
            path="$.definition.graph.edges",
            reason="missing_required",
            meta={"field": "priority"},
        )
    if message.startswith("AMBIGUOUS_TRANSITION: "):
        return FieldSchemaValidationError(
            message=message,
            path="$.definition.graph.edges",
            reason="ambiguous_transition",
            meta={},
        )
    if message.startswith("wizard_definition ordering violated: "):
        return FieldSchemaValidationError(
            message=message,
            path="$.definition.graph.nodes",
            reason="pinned_order",
            meta={},
        )
    return FieldSchemaValidationError(
        message=message,
        path="$.definition",
        reason="invalid_constraints",
        meta={},
    )


def _raise_v3_editor_authority_error(version: Any) -> None:
    raise FieldSchemaValidationError(
        message="definition must be WizardDefinition v3 for editor authority",
        path="$.definition.version",
        reason="invalid_enum",
        meta={"allowed": [3], "value": version},
    )


def _get_flow_config(engine: Any) -> dict[str, Any]:
    from .editor_storage import get_flow_config_draft

    fs = _engine_fs(engine)
    cfg = get_flow_config_draft(fs)
    return {"config": normalize_flow_config(cfg)}


def _set_flow_config(engine: Any, body: Any) -> dict[str, Any]:
    from .editor_storage import put_flow_config_draft

    obj = _validate_wrapper(body=body, required_key="config", allowed_keys={"config"})
    cfg_any = obj.get("config")
    cfg = validate_flow_config_editor_boundary(cfg_any)
    cfg = put_flow_config_draft(_engine_fs(engine), cfg)
    return {"config": cfg}


def _validate_flow_config(engine: Any, body: Any) -> dict[str, Any]:
    obj = _validate_wrapper(body=body, required_key="config", allowed_keys={"config"})
    cfg = validate_flow_config_editor_boundary(obj.get("config"))
    return {"config": cfg}


def _reset_flow_config(engine: Any) -> dict[str, Any]:
    from .editor_storage import reset_flow_config_draft

    fs = _engine_fs(engine)
    cfg = reset_flow_config_draft(fs)
    return {"config": cfg}


def _activate_flow_config(engine: Any) -> dict[str, Any]:
    from .editor_storage import activate_flow_config_draft

    fs = _engine_fs(engine)
    cfg = activate_flow_config_draft(fs)
    return {"config": normalize_flow_config(cfg)}


def _flow_config_history(engine: Any) -> dict[str, Any]:
    from .editor_storage import list_history

    fs = _engine_fs(engine)
    ids = list_history(fs, kind="flow_config")
    return _history_items(ids[:5])


def _rollback_flow_config(engine: Any, body: Any) -> dict[str, Any]:
    from .editor_storage import delete_flow_config_draft, list_history, load_flow_config, rollback

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
    delete_flow_config_draft(fs)
    cfg = load_flow_config(fs)
    return {"config": normalize_flow_config(cfg)}


def _active_step_projection(engine: Any) -> dict[str, dict[str, Any]]:
    from .editor_storage import ensure_flow_config_active_exists
    from .step_catalog import build_step_catalog_projection
    from .wizard_definition_model import load_or_bootstrap_wizard_definition

    fs = _engine_fs(engine)
    wizard_definition = load_or_bootstrap_wizard_definition(fs)
    flow_config = ensure_flow_config_active_exists(fs)
    return build_step_catalog_projection(
        wizard_definition=wizard_definition,
        flow_config=flow_config,
    )


def _get_steps_index(engine: Any) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for step_id, det in _active_step_projection(engine).items():
        kind, pinned = _classify_step(step_id)
        desc = str(det.get("description") or det.get("behavioralSummary") or "")
        short = desc.split("\n", 1)[0].strip()
        if len(short) > 120:
            short = short[:117].rstrip() + "..."
        items.append(
            {
                "step_id": step_id,
                "displayName": str(det.get("displayName") or det.get("title") or step_id),
                "shortDescription": short,
                "kind": kind,
                "pinned": pinned,
            }
        )
    return {"items": items}


def _get_transition_condition_prefixes() -> dict[str, Any]:
    return {"items": list(_TRANSITION_CONDITION_PREFIXES)}


def _get_step_details(engine: Any, step_id: Any) -> dict[str, Any]:
    sid = _ensure_ascii_step_id(step_id)
    details = _active_step_projection(engine).get(sid)
    if details is None:
        return error_envelope(
            "NOT_FOUND",
            "not found",
            details=[{"path": "$.step_id", "reason": "not_found", "meta": {}}],
        )

    kind, pinned = _classify_step(sid)
    return {
        "id": sid,
        "step_id": sid,
        "title": str(details.get("title") or sid),
        "displayName": str(details.get("displayName") or details.get("title") or sid),
        "description": str(details.get("description") or ""),
        "behavioralSummary": str(details.get("behavioralSummary") or ""),
        "inputContract": str(details.get("inputContract") or ""),
        "outputContract": str(details.get("outputContract") or ""),
        "sideEffectsDescription": str(details.get("sideEffectsDescription") or ""),
        "kind": kind,
        "pinned": pinned != "none",
        "settings_schema": dict(details.get("settings_schema") or {}),
        "defaults_template": dict(details.get("defaults_template") or {}),
    }


def _get_wizard_definition(engine: Any) -> dict[str, Any]:
    from .wizard_editor_storage import get_wizard_definition_draft

    fs = _engine_fs(engine)
    wd = get_wizard_definition_draft(fs)
    return {"definition": wd}


def _get_primitive_registry(engine: Any) -> dict[str, Any]:
    from .dsl.primitive_registry_storage import load_or_bootstrap_primitive_registry

    fs = _engine_fs(engine)
    reg = load_or_bootstrap_primitive_registry(fs)
    return {"registry": reg}


def _set_wizard_definition(engine: Any, body: Any) -> dict[str, Any]:
    from .wizard_editor_storage import put_wizard_definition_draft

    obj = _validate_wrapper(
        body=body,
        required_key="definition",
        allowed_keys={"definition"},
    )
    wd_any = obj.get("definition")
    validated = _validate_wizard_definition(engine, {"definition": wd_any})
    wd = put_wizard_definition_draft(
        _engine_fs(engine),
        validated.get("definition"),
    )
    return {"definition": wd}


def _validate_wizard_definition(engine: Any, body: Any) -> dict[str, Any]:
    obj = _validate_wrapper(
        body=body,
        required_key="definition",
        allowed_keys={"definition"},
    )
    wd_any = obj.get("definition")

    try:
        _validate_v2_editor_only_rules(wd_any)
        validate_wizard_definition_structure(wd_any)
        wd_canon = canonicalize_wizard_definition(wd_any)

        if not isinstance(wd_canon, dict):
            raise FieldSchemaValidationError(
                message="definition must be an object",
                path="$.definition",
                reason="invalid_type",
                meta={},
            )

        ver = wd_canon.get("version")
        if ver != 3:
            _raise_v3_editor_authority_error(ver)

        from .dsl.primitive_registry_storage import load_or_bootstrap_primitive_registry
        from .dsl.wizard_definition_v3_model import (
            validate_wizard_definition_v3_against_registry,
        )

        registry = load_or_bootstrap_primitive_registry(_engine_fs(engine))
        validate_wizard_definition_v3_against_registry(wd_canon, registry)
        return {"definition": wd_canon}
    except FinalizeError as err:
        raise _translate_v2_definition_error(err) from err
    except FieldSchemaValidationError:
        raise
    except Exception as err:
        raise FieldSchemaValidationError(
            message=str(err),
            path="$.definition",
            reason="invalid_constraints",
            meta={},
        ) from err


def _reset_wizard_definition(engine: Any) -> dict[str, Any]:
    from .wizard_editor_storage import reset_wizard_definition_draft

    fs = _engine_fs(engine)
    wd = reset_wizard_definition_draft(fs)
    return {"definition": wd}


def _activate_wizard_definition(engine: Any) -> dict[str, Any]:
    from .wizard_editor_storage import activate_wizard_definition_draft

    fs = _engine_fs(engine)
    wd = activate_wizard_definition_draft(fs)
    return {"definition": wd}


def _wizard_definition_history(engine: Any) -> dict[str, Any]:
    from .wizard_editor_storage import list_wizard_definition_history

    fs = _engine_fs(engine)
    ids = list_wizard_definition_history(fs)
    return _history_items(ids[:5])


def _rollback_wizard_definition(engine: Any, body: Any) -> dict[str, Any]:
    from .wizard_editor_storage import (
        delete_wizard_definition_draft,
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
    delete_wizard_definition_draft(fs)
    wd = load_wizard_definition(fs)
    return {"definition": wd}
