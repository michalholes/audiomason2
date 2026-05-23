"""WizardDefinition v3 wire model (import plugin).

WizardDefinition v3 is a DSL program model represented as a single JSON document.
This module validates the v3 wire shape and provides ordering-only canonicalization.

The interpreter/runtime for v3 is out of scope for this module.

ASCII-only.
"""

from __future__ import annotations

import re
from copy import deepcopy
from typing import NoReturn, TypeGuard

from ..field_schema_validation import FieldSchemaValidationError
from .primitive_registry_model import primitive_index

_STEP_ID_RE = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")
_ALLOWED_TOP_LEVEL_KEYS = {"version", "entry_step_id", "nodes", "edges", "libraries", "macros"}


def _raise(
    message: str,
    *,
    path: str,
    reason: str,
    meta: dict[str, object] | None = None,
) -> NoReturn:
    raise FieldSchemaValidationError(
        message=message,
        path=path,
        reason=reason,
        meta={} if meta is None else dict(meta),
    )


def _ascii_only(value: str, *, path: str) -> None:
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        _raise("value must be ASCII-only", path=path, reason="non_ascii")


def _validate_step_id(value: str, *, path: str) -> None:
    _ascii_only(value, path=path)
    if "." in value or _STEP_ID_RE.fullmatch(value) is None:
        _raise(
            "step_id must be ASCII lower_snake_case without dots",
            path=path,
            reason="missing_or_invalid",
        )


def _validate_name(value: str, *, path: str) -> None:
    _validate_step_id(value, path=path)


def _assert_exact_keys(obj: dict[str, object], *, allowed: set[str], path: str) -> None:
    unknown = sorted(set(obj.keys()) - allowed)
    if unknown:
        _raise(
            "unknown field",
            path=f"{path}.{unknown[0]}",
            reason="unknown_field",
            meta={"allowed": sorted(allowed), "unknown": unknown},
        )


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


def _as_str_list(value: object) -> list[str]:
    if not _is_object_list(value):
        return []
    return [item for item in value if isinstance(item, str)]


def _as_dict_list(value: object) -> list[dict[str, object]]:
    if not _is_object_list(value):
        return []
    return [dict(item) for item in value if _is_str_object_dict(item)]


def _write_sort_key(item: dict[str, object]) -> str:
    return str(item.get("to_path") or "")


def _name_sort_key(item: dict[str, object]) -> str:
    return str(item.get("name") or "")


def _edge_sort_key(item: dict[str, object]) -> tuple[str, str, str]:
    condition = _as_str_object_dict(item.get("condition_expr"))
    return (
        str(item.get("from") or ""),
        str(item.get("to") or ""),
        str(condition.get("expr") or ""),
    )


def _is_expr_ref(value: object) -> TypeGuard[dict[str, str]]:
    return (
        _is_str_object_dict(value)
        and set(value.keys()) == {"expr"}
        and isinstance(value.get("expr"), str)
    )


def _validate_expr_ref(value: object, *, path: str) -> None:
    if not _is_expr_ref(value):
        _raise(
            'ExprRef must be encoded as an object {"expr": "<string>"}',
            path=path,
            reason="invalid_expr_ref",
        )
    expr = value.get("expr")
    if not isinstance(expr, str) or not expr:
        _raise("expr must be a non-empty string", path=f"{path}.expr", reason="missing_or_invalid")
    _ascii_only(expr, path=f"{path}.expr")


def _validate_json_like(value: object, *, path: str) -> None:
    if _is_expr_ref(value):
        _validate_expr_ref(value, path=path)
        return
    if _is_str_object_dict(value):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                _raise("object keys must be non-empty strings", path=path, reason="invalid_type")
            _ascii_only(key, path=f"{path}.{key}")
            _validate_json_like(item, path=f"{path}.{key}")
        return
    if _is_object_list(value):
        for index, item in enumerate(value):
            _validate_json_like(item, path=f"{path}[{index}]")
        return
    if value is None or isinstance(value, (int, float, bool)):
        return
    if isinstance(value, str):
        _ascii_only(value, path=path)
        return
    _raise("value must be JSON-compatible", path=path, reason="invalid_type")


def _validate_params(params_any: object, *, path: str) -> list[dict[str, object]]:
    if not _is_object_list(params_any):
        _raise("params must be a list", path=path, reason="invalid_type")
    params: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, param_any in enumerate(params_any):
        pfx = f"{path}[{index}]"
        if not _is_str_object_dict(param_any):
            _raise("param entry must be an object", path=pfx, reason="invalid_type")
        param = dict(param_any)
        _assert_exact_keys(param, allowed={"name", "required"}, path=pfx)
        name = param.get("name")
        required = param.get("required")
        if not isinstance(name, str) or not name:
            _raise(
                "param name must be a non-empty string",
                path=f"{pfx}.name",
                reason="missing_or_invalid",
            )
        _validate_name(name, path=f"{pfx}.name")
        if name in seen:
            _raise(
                "param name must be unique",
                path=f"{pfx}.name",
                reason="duplicate",
                meta={"name": name},
            )
        if not isinstance(required, bool):
            _raise("param required must be bool", path=f"{pfx}.required", reason="invalid_type")
        seen.add(name)
        params.append({"name": name, "required": required})
    return params


def _validate_macro_defs(macros_any: object) -> dict[str, dict[str, object]]:
    if macros_any is None:
        return {}
    if not _is_str_object_dict(macros_any):
        _raise("macros must be an object", path="$.macros", reason="invalid_type")
    macros: dict[str, dict[str, object]] = {}
    for macro_id, macro_any in sorted(macros_any.items()):
        path = f"$.macros.{macro_id}"
        if not isinstance(macro_id, str) or not macro_id:
            _raise(
                "macro id must be a non-empty string",
                path="$.macros",
                reason="missing_or_invalid",
            )
        _validate_name(macro_id, path=f"{path}")
        if not _is_str_object_dict(macro_any):
            _raise("macro definition must be an object", path=path, reason="invalid_type")
        macro = dict(macro_any)
        _assert_exact_keys(macro, allowed={"params", "template"}, path=path)
        params_any = macro.get("params")
        if not _is_object_list(params_any):
            _raise("macro params must be a list", path=f"{path}.params", reason="invalid_type")
        params: list[str] = []
        seen: set[str] = set()
        for index, name_any in enumerate(params_any):
            pfx = f"{path}.params[{index}]"
            if not isinstance(name_any, str) or not name_any:
                _raise(
                    "macro param must be a non-empty string",
                    path=pfx,
                    reason="missing_or_invalid",
                )
            _validate_name(name_any, path=pfx)
            if name_any in seen:
                _raise(
                    "macro param must be unique",
                    path=pfx,
                    reason="duplicate",
                    meta={"name": name_any},
                )
            seen.add(name_any)
            params.append(name_any)
        template = macro.get("template")
        if not _is_str_object_dict(template):
            _raise(
                "macro template must be an object",
                path=f"{path}.template",
                reason="invalid_type",
            )
        macros[macro_id] = {"params": params, "template": deepcopy(template)}
    return macros


def _expand_value(
    value: object,
    *,
    macros: dict[str, dict[str, object]],
    path: str,
    args: dict[str, object] | None = None,
    stack: tuple[str, ...] = (),
) -> object:
    if _is_str_object_dict(value):
        keys = set(value.keys())
        if keys == {"param_ref"}:
            name = value.get("param_ref")
            if not isinstance(name, str) or not name:
                _raise(
                    "param_ref must be a non-empty string",
                    path=f"{path}.param_ref",
                    reason="missing_or_invalid",
                )
            _validate_name(name, path=f"{path}.param_ref")
            if args is None or name not in args:
                _raise("macro argument is required", path=f"{path}.param_ref", reason="not_found")
            return deepcopy(args[name])
        if keys == {"macro_ref", "args"}:
            macro_id = value.get("macro_ref")
            if not isinstance(macro_id, str) or not macro_id:
                _raise(
                    "macro_ref must be a non-empty string",
                    path=f"{path}.macro_ref",
                    reason="missing_or_invalid",
                )
            _validate_name(macro_id, path=f"{path}.macro_ref")
            if macro_id not in macros:
                _raise(
                    "macro_ref must reference a known macro",
                    path=f"{path}.macro_ref",
                    reason="not_found",
                )
            if macro_id in stack:
                _raise(
                    "macro expansion cycles are forbidden",
                    path=f"{path}.macro_ref",
                    reason="cycle",
                    meta={"cycle": list(stack + (macro_id,))},
                )
            args_any = value.get("args")
            if not _is_str_object_dict(args_any):
                _raise("macro args must be an object", path=f"{path}.args", reason="invalid_type")
            resolved_args = {
                key: _expand_value(
                    item,
                    macros=macros,
                    path=f"{path}.args.{key}",
                    args=args,
                    stack=stack,
                )
                for key, item in args_any.items()
            }
            expected = _as_str_list(macros[macro_id].get("params"))
            missing = [name for name in expected if name not in resolved_args]
            unknown = sorted(set(resolved_args) - set(expected))
            if missing:
                _raise(
                    "macro args must bind every declared param",
                    path=f"{path}.args",
                    reason="missing_or_invalid",
                    meta={"missing": missing, "macro_id": macro_id},
                )
            if unknown:
                _raise(
                    "macro args contain unknown binding",
                    path=f"{path}.args.{unknown[0]}",
                    reason="unknown_field",
                    meta={"unknown": unknown, "macro_id": macro_id},
                )
            return _expand_value(
                macros[macro_id]["template"],
                macros=macros,
                path=path,
                args=resolved_args,
                stack=stack + (macro_id,),
            )
        return {
            key: _expand_value(
                item,
                macros=macros,
                path=f"{path}.{key}",
                args=args,
                stack=stack,
            )
            for key, item in value.items()
        }
    if _is_object_list(value):
        return [
            _expand_value(item, macros=macros, path=f"{path}[{index}]", args=args, stack=stack)
            for index, item in enumerate(value)
        ]
    return deepcopy(value)


def _expand_program(
    wd: dict[str, object], macros: dict[str, dict[str, object]]
) -> dict[str, object]:
    out = deepcopy(wd)
    out["nodes"] = _expand_value(out.get("nodes"), macros=macros, path="$.nodes")
    out["edges"] = _expand_value(out.get("edges"), macros=macros, path="$.edges")
    libraries_any = out.get("libraries")
    if _is_str_object_dict(libraries_any):
        out["libraries"] = {
            key: {
                **dict(lib_any),
                "nodes": _expand_value(
                    dict(lib_any).get("nodes"),
                    macros=macros,
                    path=f"$.libraries.{key}.nodes",
                ),
                "edges": _expand_value(
                    dict(lib_any).get("edges"),
                    macros=macros,
                    path=f"$.libraries.{key}.edges",
                ),
            }
            for key, lib_any in libraries_any.items()
            if _is_str_object_dict(lib_any)
        }
    return out


def _resolve_library_id(
    libraries: dict[str, dict[str, object]],
    *,
    target_library: str,
    target_subflow: str,
    path: str,
) -> str:
    if target_subflow in libraries:
        if target_library and target_library != target_subflow and target_library in libraries:
            _raise(
                "target_library and target_subflow resolve ambiguously",
                path=path,
                reason="ambiguous_target",
            )
        return target_subflow
    if target_library in libraries:
        return target_library
    _raise(
        "target_library/target_subflow must reference a known library",
        path=path,
        reason="not_found",
    )
    raise AssertionError("unreachable")


def _validate_bindings(
    bindings_any: object,
    *,
    params: list[dict[str, object]],
    path: str,
) -> list[dict[str, object]]:
    if not _is_object_list(bindings_any):
        _raise("param_bindings must be a list", path=path, reason="invalid_type")
    bindings: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, binding_any in enumerate(bindings_any):
        pfx = f"{path}[{index}]"
        if not _is_str_object_dict(binding_any):
            _raise("param binding must be an object", path=pfx, reason="invalid_type")
        binding = dict(binding_any)
        _assert_exact_keys(binding, allowed={"name", "value"}, path=pfx)
        name = binding.get("name")
        if not isinstance(name, str) or not name:
            _raise(
                "binding name must be a non-empty string",
                path=f"{pfx}.name",
                reason="missing_or_invalid",
            )
        _validate_name(name, path=f"{pfx}.name")
        if name in seen:
            _raise("binding name must be unique", path=f"{pfx}.name", reason="duplicate")
        seen.add(name)
        _validate_json_like(binding.get("value"), path=f"{pfx}.value")
        bindings.append({"name": name, "value": deepcopy(binding.get("value"))})
    param_map = {str(param["name"]): bool(param["required"]) for param in params}
    unknown = sorted(seen - set(param_map))
    missing = sorted(name for name, required in param_map.items() if required and name not in seen)
    if unknown:
        _raise(
            "param_bindings contain unknown binding",
            path=f"{path}[0].name" if bindings else path,
            reason="unknown_field",
            meta={"unknown": unknown},
        )
    if missing:
        _raise(
            "param_bindings are missing required binding",
            path=path,
            reason="missing_or_invalid",
            meta={"missing": missing},
        )
    return bindings


def _validate_flow_invoke_inputs(
    inputs: dict[str, object],
    *,
    libraries: dict[str, dict[str, object]],
    path: str,
) -> None:
    _assert_exact_keys(
        inputs,
        allowed={"target_library", "target_subflow", "param_bindings"},
        path=path,
    )
    target_library = inputs.get("target_library")
    target_subflow = inputs.get("target_subflow")
    if not isinstance(target_library, str) or not target_library:
        _raise(
            "target_library must be a non-empty string",
            path=f"{path}.target_library",
            reason="missing_or_invalid",
        )
    if not isinstance(target_subflow, str) or not target_subflow:
        _raise(
            "target_subflow must be a non-empty string",
            path=f"{path}.target_subflow",
            reason="missing_or_invalid",
        )
    _validate_name(target_library, path=f"{path}.target_library")
    _validate_name(target_subflow, path=f"{path}.target_subflow")
    library_id = _resolve_library_id(
        libraries,
        target_library=target_library,
        target_subflow=target_subflow,
        path=f"{path}.target_subflow",
    )
    params = _as_dict_list(libraries[library_id].get("params"))
    _validate_bindings(inputs.get("param_bindings"), params=params, path=f"{path}.param_bindings")


def _validate_fork_join_inputs(
    inputs: dict[str, object],
    *,
    libraries: dict[str, dict[str, object]],
    path: str,
) -> None:
    _assert_exact_keys(
        inputs,
        allowed={"branch_order", "join_policy", "merge_mode", "branches"},
        path=path,
    )
    branch_order = inputs.get("branch_order")
    branches_any = inputs.get("branches")
    if not _is_object_list(branch_order) or not branch_order:
        _raise(
            "branch_order must be a non-empty list",
            path=f"{path}.branch_order",
            reason="invalid_type",
        )
    if not _is_str_object_dict(branches_any) or not branches_any:
        _raise(
            "branches must be a non-empty object",
            path=f"{path}.branches",
            reason="invalid_type",
        )
    seen: set[str] = set()
    branch_ids: list[str] = []
    for index, branch_id_any in enumerate(branch_order):
        pfx = f"{path}.branch_order[{index}]"
        if not isinstance(branch_id_any, str) or not branch_id_any:
            _raise("branch id must be a non-empty string", path=pfx, reason="missing_or_invalid")
        _validate_name(branch_id_any, path=pfx)
        if branch_id_any in seen:
            _raise("branch_order must be unique", path=pfx, reason="duplicate")
        seen.add(branch_id_any)
        branch_ids.append(branch_id_any)
    if sorted(seen) != sorted(str(key) for key in branches_any):
        _raise(
            "branches keys must match branch_order exactly",
            path=f"{path}.branches",
            reason="missing_or_invalid",
        )
    for key in ("join_policy", "merge_mode"):
        value = inputs.get(key)
        if not isinstance(value, str) or not value:
            _raise(
                f"{key} must be a non-empty string",
                path=f"{path}.{key}",
                reason="missing_or_invalid",
            )
        _ascii_only(value, path=f"{path}.{key}")
    for branch_id in branch_ids:
        spec_any = branches_any.get(branch_id)
        bfx = f"{path}.branches.{branch_id}"
        if not _is_str_object_dict(spec_any):
            _raise("branch spec must be an object", path=bfx, reason="invalid_type")
        _validate_flow_invoke_inputs(dict(spec_any), libraries=libraries, path=bfx)


def _validate_loop_inputs(inputs: dict[str, object], *, path: str) -> None:
    _assert_exact_keys(
        inputs,
        allowed={
            "iterable_expr",
            "item_var",
            "max_iterations",
            "target_library",
            "target_subflow",
            "param_bindings",
        },
        path=path,
    )
    _validate_expr_ref(inputs.get("iterable_expr"), path=f"{path}.iterable_expr")
    item_var = inputs.get("item_var")
    if not isinstance(item_var, str) or not item_var:
        _raise(
            "item_var must be a non-empty string",
            path=f"{path}.item_var",
            reason="missing_or_invalid",
        )
    _validate_name(item_var, path=f"{path}.item_var")
    max_iterations = inputs.get("max_iterations")
    if not isinstance(max_iterations, int) or max_iterations < 1:
        _raise(
            "max_iterations must be a positive integer",
            path=f"{path}.max_iterations",
            reason="missing_or_invalid",
        )
    target_library = inputs.get("target_library")
    target_subflow = inputs.get("target_subflow")
    param_bindings = inputs.get("param_bindings")
    has_invoke = any(
        value is not None for value in (target_library, target_subflow, param_bindings)
    )
    if not has_invoke:
        return
    if (
        not isinstance(target_library, str)
        or not target_library
        or not isinstance(target_subflow, str)
        or not target_subflow
    ):
        _raise(
            "loop subflow invocation requires target_library and target_subflow",
            path=path,
            reason="missing_or_invalid",
        )
    _validate_name(target_library, path=f"{path}.target_library")
    _validate_name(target_subflow, path=f"{path}.target_subflow")
    if not _is_object_list(param_bindings):
        _raise(
            "param_bindings must be a list when loop subflow invocation is configured",
            path=f"{path}.param_bindings",
            reason="invalid_type",
        )
    for index, binding_any in enumerate(param_bindings):
        bfx = f"{path}.param_bindings[{index}]"
        if not _is_str_object_dict(binding_any):
            _raise("binding must be an object", path=bfx, reason="invalid_type")
        binding = dict(binding_any)
        _assert_exact_keys(binding, allowed={"name", "value"}, path=bfx)
        name = binding.get("name")
        if not isinstance(name, str) or not name:
            _raise(
                "binding.name must be a non-empty string",
                path=f"{bfx}.name",
                reason="missing_or_invalid",
            )
        _validate_name(name, path=f"{bfx}.name")
        _validate_json_like(binding.get("value"), path=f"{bfx}.value")


def _validate_call_invoke_inputs(inputs: dict[str, object], *, path: str) -> None:
    _assert_exact_keys(
        inputs,
        allowed={"operation_id", "execution_mode", "error_mode", "args"},
        path=path,
    )
    operation_id = inputs.get("operation_id")
    if not isinstance(operation_id, str) or not operation_id:
        _raise(
            "operation_id must be a non-empty string",
            path=f"{path}.operation_id",
            reason="missing_or_invalid",
        )
    _ascii_only(operation_id, path=f"{path}.operation_id")
    execution_mode = inputs.get("execution_mode")
    if not isinstance(execution_mode, str) or execution_mode not in {"inline", "job"}:
        _raise(
            "execution_mode must be one of: inline, job",
            path=f"{path}.execution_mode",
            reason="invalid_enum",
            meta={"allowed": ["inline", "job"]},
        )
    error_mode = inputs.get("error_mode")
    if error_mode is not None and (
        not isinstance(error_mode, str) or error_mode not in {"raise", "capture"}
    ):
        _raise(
            "error_mode must be one of: raise, capture",
            path=f"{path}.error_mode",
            reason="invalid_enum",
            meta={"allowed": ["raise", "capture"]},
        )
    args_any = inputs.get("args")
    if not _is_str_object_dict(args_any):
        _raise("args must be an object", path=f"{path}.args", reason="invalid_type")


def _validate_write(write_any: object, *, step_id: str, path: str) -> None:
    if not _is_str_object_dict(write_any):
        _raise("writes entry must be an object", path=path, reason="invalid_type")
    write = dict(write_any)
    _assert_exact_keys(write, allowed={"to_path", "value"}, path=path)
    to_path = write.get("to_path")
    if not isinstance(to_path, str) or not to_path:
        _raise(
            "to_path must be a non-empty string",
            path=f"{path}.to_path",
            reason="missing_or_invalid",
        )
    _ascii_only(to_path, path=f"{path}.to_path")
    if to_path.startswith("$.state.vars."):
        pass
    elif to_path.startswith("$.state.answers."):
        rest = to_path[len("$.state.answers.") :]
        if rest != step_id and not rest.startswith(step_id + "."):
            _raise(
                "cross-step writes to answers are forbidden",
                path=f"{path}.to_path",
                reason="cross_step_write",
                meta={"step_id": step_id, "to_path": to_path},
            )
    else:
        _raise(
            "to_path must target $.state.vars.* or $.state.answers.<step_id>.*",
            path=f"{path}.to_path",
            reason="invalid_target",
            meta={"step_id": step_id, "to_path": to_path},
        )
    _validate_json_like(write.get("value"), path=f"{path}.value")


def _validate_graph(
    body: dict[str, object],
    *,
    path: str,
    libraries: dict[str, dict[str, object]],
) -> None:
    entry = body.get("entry_step_id")
    if not isinstance(entry, str) or not entry:
        _raise(
            "entry_step_id must be a non-empty string",
            path=f"{path}.entry_step_id",
            reason="missing_or_invalid",
        )
    _validate_step_id(entry, path=f"{path}.entry_step_id")
    nodes_any = body.get("nodes")
    if not _is_object_list(nodes_any):
        _raise("nodes must be a list", path=f"{path}.nodes", reason="invalid_type")
    edges_any = body.get("edges")
    if not _is_object_list(edges_any):
        _raise("edges must be a list", path=f"{path}.edges", reason="invalid_type")
    seen: set[str] = set()
    step_ids: list[str] = []
    for index, node_any in enumerate(nodes_any):
        nfx = f"{path}.nodes[{index}]"
        if not _is_str_object_dict(node_any):
            _raise("node must be an object", path=nfx, reason="invalid_type")
        node = dict(node_any)
        _assert_exact_keys(node, allowed={"step_id", "op"}, path=nfx)
        step_id = node.get("step_id")
        if not isinstance(step_id, str) or not step_id:
            _raise(
                "step_id must be a non-empty string",
                path=f"{nfx}.step_id",
                reason="missing_or_invalid",
            )
        _validate_step_id(step_id, path=f"{nfx}.step_id")
        if step_id in seen:
            _raise("step_id must be unique", path=f"{nfx}.step_id", reason="duplicate")
        seen.add(step_id)
        step_ids.append(step_id)
        op_any = node.get("op")
        if not _is_str_object_dict(op_any):
            _raise("op must be an object", path=f"{nfx}.op", reason="invalid_type")
        op = dict(op_any)
        _assert_exact_keys(
            op,
            allowed={"primitive_id", "primitive_version", "inputs", "writes"},
            path=f"{nfx}.op",
        )
        primitive_id = op.get("primitive_id")
        primitive_version = op.get("primitive_version")
        if not isinstance(primitive_id, str) or not primitive_id:
            _raise(
                "primitive_id must be a non-empty string",
                path=f"{nfx}.op.primitive_id",
                reason="missing_or_invalid",
            )
        _ascii_only(primitive_id, path=f"{nfx}.op.primitive_id")
        if not isinstance(primitive_version, int):
            _raise(
                "primitive_version must be int",
                path=f"{nfx}.op.primitive_version",
                reason="invalid_type",
            )
        inputs_any = op.get("inputs")
        if not _is_str_object_dict(inputs_any):
            _raise("inputs must be an object", path=f"{nfx}.op.inputs", reason="invalid_type")
        for key, value in inputs_any.items():
            if not isinstance(key, str) or not key:
                _raise(
                    "inputs keys must be non-empty strings",
                    path=f"{nfx}.op.inputs",
                    reason="invalid_type",
                )
            _ascii_only(key, path=f"{nfx}.op.inputs.{key}")
            _validate_json_like(value, path=f"{nfx}.op.inputs.{key}")
        if primitive_id == "parallel.fork_join" and primitive_version == 1:
            _validate_fork_join_inputs(inputs_any, libraries=libraries, path=f"{nfx}.op.inputs")
        elif primitive_id == "flow.invoke" and primitive_version == 1:
            _validate_flow_invoke_inputs(inputs_any, libraries=libraries, path=f"{nfx}.op.inputs")
        elif primitive_id == "flow.loop" and primitive_version == 1:
            _validate_loop_inputs(inputs_any, path=f"{nfx}.op.inputs")
        elif primitive_id == "call.invoke" and primitive_version == 1:
            _validate_call_invoke_inputs(inputs_any, path=f"{nfx}.op.inputs")
        writes_any = op.get("writes")
        if not _is_object_list(writes_any):
            _raise("writes must be a list", path=f"{nfx}.op.writes", reason="invalid_type")
        for w_index, write_any in enumerate(writes_any):
            _validate_write(write_any, step_id=step_id, path=f"{nfx}.op.writes[{w_index}]")
    if entry not in seen:
        _raise(
            "entry_step_id must reference an existing node step_id",
            path=f"{path}.entry_step_id",
            reason="not_found",
            meta={"entry_step_id": entry, "known": sorted(step_ids)},
        )
    for index, edge_any in enumerate(edges_any):
        efx = f"{path}.edges[{index}]"
        if not _is_str_object_dict(edge_any):
            _raise("edge must be an object", path=efx, reason="invalid_type")
        edge = dict(edge_any)
        _assert_exact_keys(edge, allowed={"from", "to", "condition_expr"}, path=efx)
        frm = edge.get("from")
        to = edge.get("to")
        if not isinstance(frm, str) or not frm:
            _raise(
                "edge.from must be a non-empty string",
                path=f"{efx}.from",
                reason="missing_or_invalid",
            )
        if not isinstance(to, str) or not to:
            _raise(
                "edge.to must be a non-empty string",
                path=f"{efx}.to",
                reason="missing_or_invalid",
            )
        _ascii_only(frm, path=f"{efx}.from")
        _ascii_only(to, path=f"{efx}.to")
        if frm not in seen:
            _raise(
                "edge.from must reference an existing node",
                path=f"{efx}.from",
                reason="not_found",
            )
        if to not in seen:
            _raise("edge.to must reference an existing node", path=f"{efx}.to", reason="not_found")
        cond = edge.get("condition_expr")
        if cond is not None:
            _validate_expr_ref(cond, path=f"{efx}.condition_expr")


def _validated_libraries(wd: dict[str, object]) -> dict[str, dict[str, object]]:
    libraries_any = wd.get("libraries")
    if libraries_any is None:
        return {}
    if not _is_str_object_dict(libraries_any):
        _raise("libraries must be an object", path="$.libraries", reason="invalid_type")
    libraries: dict[str, dict[str, object]] = {}
    for library_id, library_any in sorted(libraries_any.items()):
        path = f"$.libraries.{library_id}"
        if not isinstance(library_id, str) or not library_id:
            _raise(
                "library id must be a non-empty string",
                path="$.libraries",
                reason="missing_or_invalid",
            )
        _validate_name(library_id, path=path)
        if not _is_str_object_dict(library_any):
            _raise("library definition must be an object", path=path, reason="invalid_type")
        library = dict(library_any)
        _assert_exact_keys(
            library,
            allowed={"entry_step_id", "nodes", "edges", "params", "returns"},
            path=path,
        )
        library["params"] = _validate_params(library.get("params"), path=f"{path}.params")
        returns_any = library.get("returns")
        if returns_any is not None:
            if not _is_str_object_dict(returns_any):
                _raise("returns must be an object", path=f"{path}.returns", reason="invalid_type")
            for key, value in returns_any.items():
                if not isinstance(key, str) or not key:
                    _raise(
                        "returns keys must be non-empty strings",
                        path=f"{path}.returns",
                        reason="invalid_type",
                    )
                _ascii_only(key, path=f"{path}.returns.{key}")
                _validate_json_like(value, path=f"{path}.returns.{key}")
        libraries[library_id] = library
    return libraries


def _library_deps(
    library: dict[str, object], *, libraries: dict[str, dict[str, object]]
) -> set[str]:
    deps: set[str] = set()
    for node_any in _as_dict_list(library.get("nodes")):
        if not _is_str_object_dict(node_any):
            continue
        op_any = node_any.get("op")
        if not _is_str_object_dict(op_any):
            continue
        primitive_id = op_any.get("primitive_id")
        inputs_any = op_any.get("inputs")
        if not isinstance(primitive_id, str) or not _is_str_object_dict(inputs_any):
            continue
        if primitive_id == "flow.invoke":
            deps.add(
                _resolve_library_id(
                    libraries,
                    target_library=str(inputs_any.get("target_library") or ""),
                    target_subflow=str(inputs_any.get("target_subflow") or ""),
                    path="$.libraries",
                )
            )
        if primitive_id == "parallel.fork_join":
            branches_doc = _as_str_object_dict(inputs_any.get("branches"))
            for spec_any in branches_doc.values():
                if not _is_str_object_dict(spec_any):
                    continue
                deps.add(
                    _resolve_library_id(
                        libraries,
                        target_library=str(spec_any.get("target_library") or ""),
                        target_subflow=str(spec_any.get("target_subflow") or ""),
                        path="$.libraries",
                    )
                )
    return deps


def _validate_library_cycles(libraries: dict[str, dict[str, object]]) -> None:
    deps = {
        library_id: _library_deps(library, libraries=libraries)
        for library_id, library in libraries.items()
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(library_id: str, trail: tuple[str, ...]) -> None:
        if library_id in visited:
            return
        if library_id in visiting:
            _raise(
                "library cycles are forbidden",
                path=f"$.libraries.{library_id}",
                reason="cycle",
                meta={"cycle": list(trail + (library_id,))},
            )
        visiting.add(library_id)
        for dep in sorted(deps.get(library_id) or set()):
            visit(dep, trail + (library_id,))
        visiting.remove(library_id)
        visited.add(library_id)

    for library_id in sorted(libraries):
        visit(library_id, ())


def validate_wizard_definition_v3_structure(wd_any: object) -> None:
    if not _is_str_object_dict(wd_any):
        _raise("WizardDefinition v3 must be an object", path="$", reason="invalid_type")
    wd = dict(wd_any)
    _assert_exact_keys(wd, allowed=_ALLOWED_TOP_LEVEL_KEYS, path="$")
    if wd.get("version") != 3:
        _raise(
            "WizardDefinition v3 version must equal 3",
            path="$.version",
            reason="invalid_enum",
            meta={"expected": 3, "value": wd.get("version")},
        )
    macros = _validate_macro_defs(wd.get("macros"))
    expanded = _expand_program(wd, macros)
    libraries = _validated_libraries(expanded)
    _validate_graph(expanded, path="$", libraries=libraries)
    for library_id, library in libraries.items():
        _validate_graph(library, path=f"$.libraries.{library_id}", libraries=libraries)
    _validate_library_cycles(libraries)


def _canonicalize_graph(body: dict[str, object]) -> dict[str, object]:
    out = dict(body)
    nodes_any = out.get("nodes")
    if _is_object_list(nodes_any):
        nodes: list[dict[str, object]] = []
        for node_any in nodes_any:
            if not _is_str_object_dict(node_any):
                continue
            node = dict(node_any)
            op_any = node.get("op")
            if _is_str_object_dict(op_any):
                op = dict(op_any)
                writes_any = op.get("writes")
                if _is_object_list(writes_any):
                    op["writes"] = sorted(
                        _as_dict_list(writes_any),
                        key=_write_sort_key,
                    )
                inputs_any = op.get("inputs")
                if _is_str_object_dict(inputs_any):
                    inputs = dict(inputs_any)
                    bindings_any = inputs.get("param_bindings")
                    if _is_object_list(bindings_any):
                        inputs["param_bindings"] = sorted(
                            _as_dict_list(bindings_any),
                            key=_name_sort_key,
                        )
                    branches_any = inputs.get("branches")
                    if _is_str_object_dict(branches_any):
                        inputs["branches"] = {
                            key: _as_str_object_dict(branches_any.get(key))
                            for key in sorted(branches_any)
                            if _is_str_object_dict(branches_any.get(key))
                        }
                    op["inputs"] = inputs
                node["op"] = op
            nodes.append(node)
        out["nodes"] = nodes
    edges_any = out.get("edges")
    if _is_object_list(edges_any):
        out["edges"] = sorted(
            _as_dict_list(edges_any),
            key=_edge_sort_key,
        )
    return out


def canonicalize_wizard_definition_v3(wd_any: object) -> object:
    if not _is_str_object_dict(wd_any) or wd_any.get("version") != 3:
        return wd_any
    macros = _validate_macro_defs(wd_any.get("macros"))
    out = _canonicalize_graph(_expand_program(dict(wd_any), macros))
    libraries_any = out.get("libraries")
    if _is_str_object_dict(libraries_any):
        out["libraries"] = {
            library_id: {
                **_canonicalize_graph(dict(library_any)),
                "params": sorted(
                    _as_dict_list(library_any.get("params")),
                    key=_name_sort_key,
                ),
            }
            for library_id, library_any in sorted(libraries_any.items())
            if _is_str_object_dict(library_any)
        }
    if macros:
        out["macros"] = {
            macro_id: {
                "params": sorted(_as_str_list(macro.get("params"))),
                "template": deepcopy(macro["template"]),
            }
            for macro_id, macro in sorted(macros.items())
        }
    return out


def _iter_program_nodes(wd: dict[str, object]) -> list[tuple[str, int, dict[str, object]]]:
    out: list[tuple[str, int, dict[str, object]]] = []
    nodes_any = wd.get("nodes")
    if _is_object_list(nodes_any):
        for index, node_any in enumerate(nodes_any):
            if _is_str_object_dict(node_any):
                out.append(("$.nodes", index, node_any))
    libraries_any = wd.get("libraries")
    if _is_str_object_dict(libraries_any):
        for library_id, library_any in libraries_any.items():
            if not _is_str_object_dict(library_any):
                continue
            nodes_any = library_any.get("nodes")
            if not _is_object_list(nodes_any):
                continue
            for index, node_any in enumerate(nodes_any):
                if _is_str_object_dict(node_any):
                    out.append((f"$.libraries.{library_id}.nodes", index, node_any))
    return out


def validate_wizard_definition_v3_against_registry(
    wd: dict[str, object],
    registry: dict[str, object],
) -> None:
    known = primitive_index(registry)
    for base_path, index, node_any in _iter_program_nodes(wd):
        op_any = node_any.get("op")
        if not _is_str_object_dict(op_any):
            continue
        pid = op_any.get("primitive_id")
        pver = op_any.get("primitive_version")
        if not isinstance(pid, str) or not isinstance(pver, int):
            continue
        if (pid, pver) not in known:
            _raise(
                "unknown primitive_id@version referenced by WizardDefinition",
                path=f"{base_path}[{index}].op.primitive_id",
                reason="unknown_primitive",
                meta={"primitive_id": pid, "primitive_version": pver},
            )
