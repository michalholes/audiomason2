"""WizardDefinition v3 wire model (import plugin).

WizardDefinition v3 is a DSL program model represented as a single JSON document.
This module validates the v3 wire shape and provides ordering-only canonicalization.

The interpreter/runtime for v3 is out of scope for this module.

ASCII-only.
"""

from __future__ import annotations

from typing import Any, TypeGuard

from ..field_schema_validation import FieldSchemaValidationError
from .primitive_registry_model import primitive_index


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


def _is_expr_ref(value: Any) -> TypeGuard[dict[str, str]]:
    if not isinstance(value, dict):
        return False
    if set(value.keys()) != {"expr"}:
        return False
    expr = value.get("expr")
    return isinstance(expr, str)


def _validate_expr_ref(value: Any, *, path: str) -> None:
    if not _is_expr_ref(value):
        raise FieldSchemaValidationError(
            message='ExprRef must be encoded as an object {"expr": "<string>"}',
            path=path,
            reason="invalid_expr_ref",
            meta={},
        )
    expr = value.get("expr")
    if not isinstance(expr, str) or not expr:
        raise FieldSchemaValidationError(
            message="expr must be a non-empty string",
            path=f"{path}.expr",
            reason="missing_or_invalid",
            meta={},
        )
    _ascii_only(expr, path=f"{path}.expr")


def validate_wizard_definition_v3_structure(wd_any: Any) -> None:
    if not isinstance(wd_any, dict):
        raise FieldSchemaValidationError(
            message="WizardDefinition v3 must be an object",
            path="$",
            reason="invalid_type",
            meta={},
        )

    wd = dict(wd_any)
    _assert_exact_keys(wd, allowed={"version", "entry_step_id", "nodes", "edges"}, path="$")

    version = wd.get("version")
    if version != 3:
        raise FieldSchemaValidationError(
            message="WizardDefinition v3 version must equal 3",
            path="$.version",
            reason="invalid_enum",
            meta={"expected": 3, "value": version},
        )

    entry = wd.get("entry_step_id")
    if not isinstance(entry, str) or not entry:
        raise FieldSchemaValidationError(
            message="entry_step_id must be a non-empty string",
            path="$.entry_step_id",
            reason="missing_or_invalid",
            meta={},
        )
    _ascii_only(entry, path="$.entry_step_id")

    nodes_any = wd.get("nodes")
    if not isinstance(nodes_any, list):
        raise FieldSchemaValidationError(
            message="nodes must be a list",
            path="$.nodes",
            reason="invalid_type",
            meta={},
        )

    edges_any = wd.get("edges")
    if not isinstance(edges_any, list):
        raise FieldSchemaValidationError(
            message="edges must be a list",
            path="$.edges",
            reason="invalid_type",
            meta={},
        )

    step_ids: list[str] = []
    seen: set[str] = set()
    for i, n_any in enumerate(nodes_any):
        nfx = f"$.nodes[{i}]"
        if not isinstance(n_any, dict):
            raise FieldSchemaValidationError(
                message="node must be an object",
                path=nfx,
                reason="invalid_type",
                meta={},
            )
        node = dict(n_any)
        _assert_exact_keys(node, allowed={"step_id", "op"}, path=nfx)

        sid = node.get("step_id")
        if not isinstance(sid, str) or not sid:
            raise FieldSchemaValidationError(
                message="step_id must be a non-empty string",
                path=f"{nfx}.step_id",
                reason="missing_or_invalid",
                meta={},
            )
        _ascii_only(sid, path=f"{nfx}.step_id")
        if sid in seen:
            raise FieldSchemaValidationError(
                message="step_id must be unique",
                path=f"{nfx}.step_id",
                reason="duplicate",
                meta={"step_id": sid},
            )
        seen.add(sid)
        step_ids.append(sid)

        op_any = node.get("op")
        if not isinstance(op_any, dict):
            raise FieldSchemaValidationError(
                message="op must be an object",
                path=f"{nfx}.op",
                reason="invalid_type",
                meta={"step_id": sid},
            )
        op = dict(op_any)
        _assert_exact_keys(
            op,
            allowed={"primitive_id", "primitive_version", "inputs", "writes"},
            path=f"{nfx}.op",
        )

        pid = op.get("primitive_id")
        if not isinstance(pid, str) or not pid:
            raise FieldSchemaValidationError(
                message="primitive_id must be a non-empty string",
                path=f"{nfx}.op.primitive_id",
                reason="missing_or_invalid",
                meta={"step_id": sid},
            )
        _ascii_only(pid, path=f"{nfx}.op.primitive_id")

        pver = op.get("primitive_version")
        if not isinstance(pver, int):
            raise FieldSchemaValidationError(
                message="primitive_version must be int",
                path=f"{nfx}.op.primitive_version",
                reason="invalid_type",
                meta={"step_id": sid, "primitive_id": pid},
            )

        inputs_any = op.get("inputs")
        if not isinstance(inputs_any, dict):
            raise FieldSchemaValidationError(
                message="inputs must be an object",
                path=f"{nfx}.op.inputs",
                reason="invalid_type",
                meta={"step_id": sid, "primitive_id": pid},
            )
        for k in inputs_any:
            if not isinstance(k, str) or not k:
                raise FieldSchemaValidationError(
                    message="inputs keys must be non-empty strings",
                    path=f"{nfx}.op.inputs",
                    reason="invalid_type",
                    meta={"step_id": sid, "primitive_id": pid},
                )
            _ascii_only(k, path=f"{nfx}.op.inputs.{k}")
            v = inputs_any.get(k)
            if _is_expr_ref(v):
                _validate_expr_ref(v, path=f"{nfx}.op.inputs.{k}")

        writes_any = op.get("writes")
        if not isinstance(writes_any, list):
            raise FieldSchemaValidationError(
                message="writes must be a list",
                path=f"{nfx}.op.writes",
                reason="invalid_type",
                meta={"step_id": sid, "primitive_id": pid},
            )

        for j, w_any in enumerate(writes_any):
            wfx = f"{nfx}.op.writes[{j}]"
            if not isinstance(w_any, dict):
                raise FieldSchemaValidationError(
                    message="writes entry must be an object",
                    path=wfx,
                    reason="invalid_type",
                    meta={"step_id": sid},
                )
            w = dict(w_any)
            _assert_exact_keys(w, allowed={"to_path", "value"}, path=wfx)

            to_path = w.get("to_path")
            if not isinstance(to_path, str) or not to_path:
                raise FieldSchemaValidationError(
                    message="to_path must be a non-empty string",
                    path=f"{wfx}.to_path",
                    reason="missing_or_invalid",
                    meta={"step_id": sid},
                )
            _ascii_only(to_path, path=f"{wfx}.to_path")

            if to_path.startswith("$.state.vars."):
                pass
            elif to_path.startswith("$.state.answers."):
                rest = to_path[len("$.state.answers.") :]
                if rest != sid and not rest.startswith(sid + "."):
                    raise FieldSchemaValidationError(
                        message="cross-step writes to answers are forbidden",
                        path=f"{wfx}.to_path",
                        reason="cross_step_write",
                        meta={"step_id": sid, "to_path": to_path},
                    )
            else:
                raise FieldSchemaValidationError(
                    message="to_path must target $.state.vars.* or $.state.answers.<step_id>.*",
                    path=f"{wfx}.to_path",
                    reason="invalid_target",
                    meta={"step_id": sid, "to_path": to_path},
                )

            val = w.get("value")
            if _is_expr_ref(val):
                _validate_expr_ref(val, path=f"{wfx}.value")

    if entry not in seen:
        raise FieldSchemaValidationError(
            message="entry_step_id must reference an existing node step_id",
            path="$.entry_step_id",
            reason="not_found",
            meta={"entry_step_id": entry, "known": sorted(step_ids)},
        )

    for i, e_any in enumerate(edges_any):
        efx = f"$.edges[{i}]"
        if not isinstance(e_any, dict):
            raise FieldSchemaValidationError(
                message="edge must be an object",
                path=efx,
                reason="invalid_type",
                meta={},
            )
        e = dict(e_any)
        _assert_exact_keys(e, allowed={"from", "to", "condition_expr"}, path=efx)

        frm = e.get("from")
        to = e.get("to")
        if not isinstance(frm, str) or not frm:
            raise FieldSchemaValidationError(
                message="edge.from must be a non-empty string",
                path=f"{efx}.from",
                reason="missing_or_invalid",
                meta={},
            )
        if not isinstance(to, str) or not to:
            raise FieldSchemaValidationError(
                message="edge.to must be a non-empty string",
                path=f"{efx}.to",
                reason="missing_or_invalid",
                meta={},
            )
        _ascii_only(frm, path=f"{efx}.from")
        _ascii_only(to, path=f"{efx}.to")

        if frm not in seen:
            raise FieldSchemaValidationError(
                message="edge.from must reference an existing node",
                path=f"{efx}.from",
                reason="not_found",
                meta={"from": frm},
            )
        if to not in seen:
            raise FieldSchemaValidationError(
                message="edge.to must reference an existing node",
                path=f"{efx}.to",
                reason="not_found",
                meta={"to": to},
            )

        cond = e.get("condition_expr")
        if cond is not None:
            _validate_expr_ref(cond, path=f"{efx}.condition_expr")


def canonicalize_wizard_definition_v3(wd_any: Any) -> Any:
    if not isinstance(wd_any, dict):
        return wd_any

    if wd_any.get("version") != 3:
        return wd_any

    out = dict(wd_any)

    nodes_any = out.get("nodes")
    if isinstance(nodes_any, list):
        nodes: list[dict[str, Any]] = []
        for n_any in nodes_any:
            if not isinstance(n_any, dict):
                continue
            node = dict(n_any)
            op_any = node.get("op")
            if isinstance(op_any, dict):
                op = dict(op_any)
                writes_any = op.get("writes")
                if isinstance(writes_any, list):
                    writes: list[dict[str, Any]] = []
                    for w_any in writes_any:
                        if not isinstance(w_any, dict):
                            continue
                        writes.append(dict(w_any))

                    def _wkey(w: dict[str, Any]) -> str:
                        tp = w.get("to_path")
                        return str(tp) if isinstance(tp, str) else ""

                    op["writes"] = sorted(writes, key=_wkey)
                node["op"] = op
            nodes.append(node)

        def _nkey(n: dict[str, Any]) -> str:
            sid = n.get("step_id")
            return str(sid) if isinstance(sid, str) else ""

        out["nodes"] = sorted(nodes, key=_nkey)

    edges_any = out.get("edges")
    if isinstance(edges_any, list):
        edges: list[dict[str, Any]] = []
        for e_any in edges_any:
            if not isinstance(e_any, dict):
                continue
            edges.append(dict(e_any))

        def _ekey(e: dict[str, Any]) -> tuple[str, str, str]:
            frm = e.get("from")
            to = e.get("to")
            cond = e.get("condition_expr")
            expr = ""
            if isinstance(cond, dict) and isinstance(cond.get("expr"), str):
                expr = str(cond.get("expr"))
            return (
                str(frm) if isinstance(frm, str) else "",
                str(to) if isinstance(to, str) else "",
                expr,
            )

        out["edges"] = sorted(edges, key=_ekey)

    return out


def validate_wizard_definition_v3_against_registry(
    wd: dict[str, Any],
    registry: dict[str, Any],
) -> None:
    known = primitive_index(registry)

    nodes_any = wd.get("nodes")
    if not isinstance(nodes_any, list):
        return

    for i, n_any in enumerate(nodes_any):
        if not isinstance(n_any, dict):
            continue
        op_any = n_any.get("op")
        if not isinstance(op_any, dict):
            continue
        pid = op_any.get("primitive_id")
        pver = op_any.get("primitive_version")
        if not isinstance(pid, str) or not isinstance(pver, int):
            continue
        if (pid, pver) not in known:
            raise FieldSchemaValidationError(
                message="unknown primitive_id@version referenced by WizardDefinition",
                path=f"$.nodes[{i}].op.primitive_id",
                reason="unknown_primitive",
                meta={"primitive_id": pid, "primitive_version": pver},
            )
