"""Primitive registry wire model (import plugin).

The primitive registry is a runtime artifact stored under the WIZARDS root.
It is the single authoritative discovery surface for DSL primitives.

Wire shape (spec 10.19):
  {"registry_version": int, "primitives": array}

Each primitives[] entry must minimally include:
  - primitive_id (string)
  - version (int)
  - phase (int)
  - inputs_schema (object)
  - outputs_schema (object)
  - allowed_errors (array of strings)

This module additionally requires determinism_notes (string).

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from ..field_schema_validation import FieldSchemaValidationError

_ALLOWED_SCHEMA_KEYS: set[str] = {
    "type",
    "properties",
    "required",
    "items",
    "enum",
    "description",
}

_ALLOWED_SCHEMA_TYPES: set[str] = {
    "object",
    "array",
    "string",
    "number",
    "integer",
    "boolean",
    "null",
}


def _ascii_only(value: str, *, path: str) -> None:
    try:
        value.encode("ascii")
    except UnicodeEncodeError as e:
        raise FieldSchemaValidationError(
            message="value must be ASCII-only",
            path=path,
            reason="non_ascii",
            meta={},
        ) from e


def _assert_exact_keys(obj: dict[str, Any], *, allowed: set[str], path: str) -> None:
    unknown = sorted(set(obj.keys()) - allowed)
    if unknown:
        key = unknown[0]
        raise FieldSchemaValidationError(
            message="unknown field",
            path=f"{path}.{key}",
            reason="unknown_field",
            meta={"allowed": sorted(allowed), "unknown": unknown},
        )


def _validate_schema_subset(schema_any: Any, *, path: str) -> None:
    if not isinstance(schema_any, dict):
        raise FieldSchemaValidationError(
            message="schema must be an object",
            path=path,
            reason="invalid_type",
            meta={},
        )

    _assert_exact_keys(schema_any, allowed=_ALLOWED_SCHEMA_KEYS, path=path)

    stype = schema_any.get("type")
    if stype is not None:
        if not isinstance(stype, str) or not stype:
            raise FieldSchemaValidationError(
                message="schema.type must be a non-empty string",
                path=f"{path}.type",
                reason="missing_or_invalid",
                meta={"allowed": sorted(_ALLOWED_SCHEMA_TYPES)},
            )
        if stype not in _ALLOWED_SCHEMA_TYPES:
            raise FieldSchemaValidationError(
                message="schema.type must be a supported value",
                path=f"{path}.type",
                reason="invalid_enum",
                meta={"allowed": sorted(_ALLOWED_SCHEMA_TYPES), "value": stype},
            )

    desc = schema_any.get("description")
    if desc is not None and not isinstance(desc, str):
        raise FieldSchemaValidationError(
            message="schema.description must be a string",
            path=f"{path}.description",
            reason="invalid_type",
            meta={},
        )

    required = schema_any.get("required")
    if required is not None:
        if not isinstance(required, list) or not all(isinstance(x, str) for x in required):
            raise FieldSchemaValidationError(
                message="schema.required must be a list of strings",
                path=f"{path}.required",
                reason="invalid_type",
                meta={},
            )
        for i, name in enumerate(required):
            if not name:
                raise FieldSchemaValidationError(
                    message="schema.required entries must be non-empty",
                    path=f"{path}.required[{i}]",
                    reason="missing_or_invalid",
                    meta={},
                )
            _ascii_only(name, path=f"{path}.required[{i}]")

    enum = schema_any.get("enum")
    if enum is not None:
        if not isinstance(enum, list):
            raise FieldSchemaValidationError(
                message="schema.enum must be a list",
                path=f"{path}.enum",
                reason="invalid_type",
                meta={},
            )
        for i, v in enumerate(enum):
            if isinstance(v, (dict, list)):
                raise FieldSchemaValidationError(
                    message="schema.enum values must be JSON primitives",
                    path=f"{path}.enum[{i}]",
                    reason="invalid_type",
                    meta={},
                )

    props = schema_any.get("properties")
    if props is not None:
        if not isinstance(props, dict):
            raise FieldSchemaValidationError(
                message="schema.properties must be an object",
                path=f"{path}.properties",
                reason="invalid_type",
                meta={},
            )
        for k, v in props.items():
            if not isinstance(k, str) or not k:
                raise FieldSchemaValidationError(
                    message="schema.properties keys must be non-empty strings",
                    path=f"{path}.properties",
                    reason="invalid_type",
                    meta={},
                )
            _ascii_only(k, path=f"{path}.properties.{k}")
            _validate_schema_subset(v, path=f"{path}.properties.{k}")

    items = schema_any.get("items")
    if items is not None:
        _validate_schema_subset(items, path=f"{path}.items")


def _canonicalize_schema_subset(schema_any: Any) -> Any:
    if not isinstance(schema_any, dict):
        return schema_any

    out = dict(schema_any)

    req = out.get("required")
    if isinstance(req, list) and all(isinstance(x, str) for x in req):
        out["required"] = sorted(req)

    enum = out.get("enum")
    if isinstance(enum, list):
        try:
            out["enum"] = sorted(enum, key=lambda x: (str(type(x)), str(x)))
        except Exception:
            out["enum"] = list(enum)

    props = out.get("properties")
    if isinstance(props, dict):
        out["properties"] = {k: _canonicalize_schema_subset(v) for k, v in props.items()}

    items = out.get("items")
    if items is not None:
        out["items"] = _canonicalize_schema_subset(items)

    return out


def validate_primitive_registry(registry_any: Any) -> dict[str, Any]:
    if not isinstance(registry_any, dict):
        raise FieldSchemaValidationError(
            message="primitive registry must be an object",
            path="$",
            reason="invalid_type",
            meta={},
        )

    registry = dict(registry_any)
    _assert_exact_keys(
        registry,
        allowed={"registry_version", "primitives"},
        path="$",
    )

    ver = registry.get("registry_version")
    if not isinstance(ver, int):
        raise FieldSchemaValidationError(
            message="registry_version must be int",
            path="$.registry_version",
            reason="invalid_type",
            meta={},
        )

    prims_any = registry.get("primitives")
    if not isinstance(prims_any, list):
        raise FieldSchemaValidationError(
            message="primitives must be a list",
            path="$.primitives",
            reason="invalid_type",
            meta={},
        )

    for i, p_any in enumerate(prims_any):
        pfx = f"$.primitives[{i}]"
        if not isinstance(p_any, dict):
            raise FieldSchemaValidationError(
                message="primitive entry must be an object",
                path=pfx,
                reason="invalid_type",
                meta={},
            )

        p = dict(p_any)
        allowed = {
            "primitive_id",
            "version",
            "phase",
            "inputs_schema",
            "outputs_schema",
            "determinism_notes",
            "allowed_errors",
        }
        _assert_exact_keys(p, allowed=allowed, path=pfx)

        pid = p.get("primitive_id")
        if not isinstance(pid, str) or not pid:
            raise FieldSchemaValidationError(
                message="primitive_id must be a non-empty string",
                path=f"{pfx}.primitive_id",
                reason="missing_or_invalid",
                meta={},
            )
        _ascii_only(pid, path=f"{pfx}.primitive_id")

        v = p.get("version")
        if not isinstance(v, int):
            raise FieldSchemaValidationError(
                message="version must be int",
                path=f"{pfx}.version",
                reason="invalid_type",
                meta={"primitive_id": pid},
            )

        phase = p.get("phase")
        if not isinstance(phase, int):
            raise FieldSchemaValidationError(
                message="phase must be int",
                path=f"{pfx}.phase",
                reason="invalid_type",
                meta={"primitive_id": pid, "version": v},
            )

        det = p.get("determinism_notes")
        if not isinstance(det, str) or not det:
            raise FieldSchemaValidationError(
                message="determinism_notes must be a non-empty string",
                path=f"{pfx}.determinism_notes",
                reason="missing_or_invalid",
                meta={"primitive_id": pid, "version": v},
            )

        ins = p.get("inputs_schema")
        outs = p.get("outputs_schema")
        _validate_schema_subset(ins, path=f"{pfx}.inputs_schema")
        _validate_schema_subset(outs, path=f"{pfx}.outputs_schema")

        allowed_errors = p.get("allowed_errors")
        if not isinstance(allowed_errors, list) or not all(
            isinstance(x, str) and x for x in allowed_errors
        ):
            raise FieldSchemaValidationError(
                message="allowed_errors must be a list of non-empty strings",
                path=f"{pfx}.allowed_errors",
                reason="invalid_type",
                meta={"primitive_id": pid, "version": v},
            )
        for j, code in enumerate(allowed_errors):
            _ascii_only(code, path=f"{pfx}.allowed_errors[{j}]")

    return registry


def canonicalize_primitive_registry(registry_any: Any) -> Any:
    if not isinstance(registry_any, dict):
        return registry_any

    reg = dict(registry_any)
    prims_any = reg.get("primitives")
    if not isinstance(prims_any, list):
        return registry_any

    prims: list[dict[str, Any]] = []
    for p_any in prims_any:
        if not isinstance(p_any, dict):
            continue
        p = dict(p_any)
        if "inputs_schema" in p:
            p["inputs_schema"] = _canonicalize_schema_subset(p.get("inputs_schema"))
        if "outputs_schema" in p:
            p["outputs_schema"] = _canonicalize_schema_subset(p.get("outputs_schema"))
        ae = p.get("allowed_errors")
        if isinstance(ae, list) and all(isinstance(x, str) for x in ae):
            p["allowed_errors"] = sorted(ae)
        prims.append(p)

    def _key(p: dict[str, Any]) -> tuple[str, int]:
        pid = p.get("primitive_id")
        ver = p.get("version")
        return (str(pid) if isinstance(pid, str) else "", int(ver) if isinstance(ver, int) else 0)

    prims_sorted = sorted(prims, key=_key)
    out = dict(reg)
    out["primitives"] = prims_sorted
    return out


def primitive_index(registry: dict[str, Any]) -> set[tuple[str, int]]:
    prims_any = registry.get("primitives")
    if not isinstance(prims_any, list):
        return set()

    out: set[tuple[str, int]] = set()
    for p_any in prims_any:
        if not isinstance(p_any, dict):
            continue
        pid = p_any.get("primitive_id")
        ver = p_any.get("version")
        if isinstance(pid, str) and isinstance(ver, int):
            out.add((pid, ver))
    return out
