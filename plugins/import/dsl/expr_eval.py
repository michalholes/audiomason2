"""Total evaluator for the sealed ExprRef baseline language. ASCII-only."""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass
from typing import Any

from .expr_parser import (
    BinaryOpNode,
    CallNode,
    ExprAst,
    ExprParseError,
    LiteralNode,
    PathNode,
    UnaryOpNode,
    parse_expr,
)


@dataclass(frozen=True)
class ExprEvalError:
    code: str
    path: str
    reason: str
    meta: dict[str, Any]


ErrorLike = ExprParseError | ExprEvalError
EvalResult = tuple[bool, Any | None, ExprEvalError | None]


def _error(
    *, code: str, path: str, reason: str, meta: dict[str, Any] | None = None
) -> ExprEvalError:
    return ExprEvalError(
        code=code,
        path=path,
        reason=reason,
        meta={} if meta is None else dict(meta),
    )


def _fail(
    path: str,
    code: str,
    reason: str,
    meta: dict[str, Any] | None = None,
) -> EvalResult:
    return False, None, _error(code=code, path=path, reason=reason, meta=meta)


def _to_error_obj(error: ErrorLike) -> dict[str, Any]:
    obj: dict[str, Any] = {
        "code": error.code,
        "path": error.path,
        "reason": error.reason,
    }
    if error.meta:
        obj["meta"] = dict(error.meta)
    return obj


def _is_expr_ref(value: Any) -> bool:
    return (
        isinstance(value, dict) and set(value.keys()) == {"expr"} and isinstance(value["expr"], str)
    )


class _Evaluator:
    def __init__(
        self,
        *,
        state: Any,
        inputs: Any,
        op_outputs: Any,
        allow_op_outputs: bool,
        path: str,
    ) -> None:
        self._roots: dict[tuple[str, ...], Any] = {
            ("state",): state,
            ("inputs",): inputs,
            ("op", "outputs"): op_outputs,
        }
        self._allow_op_outputs = allow_op_outputs
        self._path = path

    def eval(self, node: ExprAst) -> EvalResult:
        if isinstance(node, LiteralNode):
            return True, node.value, None
        if isinstance(node, PathNode):
            return self._eval_path(node)
        if isinstance(node, UnaryOpNode):
            return self._eval_unary(node)
        if isinstance(node, BinaryOpNode):
            return self._eval_binary(node)
        if isinstance(node, CallNode):
            return self._eval_call(node)
        return _fail(
            self._path,
            "internal_error",
            "unknown_ast_node",
            {"node_type": type(node).__name__},
        )

    def _eval_path(self, node: PathNode) -> EvalResult:
        root_name = "$." + ".".join(node.root)
        if node.root == ("op", "outputs") and not self._allow_op_outputs:
            return _fail(
                self._path,
                "forbidden_root",
                "op_outputs_not_allowed",
                {"root": root_name},
            )
        if node.root not in self._roots:
            return _fail(
                self._path,
                "forbidden_root",
                "unsupported_root",
                {"root": root_name},
            )
        current = self._roots[node.root]
        current_path = root_name
        for segment in node.segments:
            if isinstance(segment, str):
                current_path = f"{current_path}.{segment}"
                if not isinstance(current, dict):
                    return _fail(
                        self._path,
                        "invalid_path_access",
                        "expected_object",
                        {"segment": segment, "root": root_name},
                    )
                if segment not in current:
                    return _fail(
                        self._path,
                        "missing_path",
                        "missing_key",
                        {"path": current_path},
                    )
                current = current[segment]
                continue
            current_path = f"{current_path}[{segment}]"
            if not isinstance(current, list):
                return _fail(
                    self._path,
                    "invalid_path_access",
                    "expected_list",
                    {"index": segment, "root": root_name},
                )
            if segment < 0 or segment >= len(current):
                return _fail(
                    self._path,
                    "missing_path",
                    "missing_index",
                    {"path": current_path},
                )
            current = current[segment]
        return True, current, None

    def _eval_unary(self, node: UnaryOpNode) -> EvalResult:
        ok, value, error = self.eval(node.operand)
        if not ok:
            return False, None, error
        if node.op != "not":
            return _fail(
                self._path,
                "internal_error",
                "unknown_unary_operator",
                {"op": node.op},
            )
        if not isinstance(value, bool):
            return _fail(
                self._path,
                "type_mismatch",
                "not_requires_bool",
                {"type": type(value).__name__},
            )
        return True, not value, None

    def _eval_binary(self, node: BinaryOpNode) -> EvalResult:
        ok_left, left, error = self.eval(node.left)
        if not ok_left:
            return False, None, error
        ok_right, right, error = self.eval(node.right)
        if not ok_right:
            return False, None, error
        op = node.op
        if op in {"and", "or"}:
            if not isinstance(left, bool) or not isinstance(right, bool):
                return _fail(
                    self._path,
                    "type_mismatch",
                    "boolean_operator_requires_bool",
                    {"op": op},
                )
            return True, (left and right) if op == "and" else (left or right), None
        if op in {"==", "!="}:
            result = left == right
            return True, result if op == "==" else not result, None
        if op in {"<", "<=", ">", ">="}:
            if (
                isinstance(left, (int, float))
                and not isinstance(left, bool)
                and isinstance(right, (int, float))
                and not isinstance(right, bool)
            ):
                return True, _compare_num(op, left, right), None
            if isinstance(left, str) and isinstance(right, str):
                return True, _compare_str(op, left, right), None
            return _fail(
                self._path,
                "type_mismatch",
                "comparison_type_mismatch",
                {"op": op},
            )
        if op == "in":
            return _eval_in(left=left, right=right, path=self._path)
        return _fail(
            self._path,
            "internal_error",
            "unknown_binary_operator",
            {"op": op},
        )

    def _eval_call(self, node: CallNode) -> EvalResult:
        values: list[Any] = []
        for arg in node.args:
            ok, value, error = self.eval(arg)
            if not ok:
                return False, None, error
            values.append(value)
        name = node.name
        if name == "len":
            return _fn_len(values, self._path)
        if name in {"any", "all"}:
            return _fn_bool_list(name, values, self._path)
        if name in {"lower", "upper"}:
            return _fn_case(name, values, self._path)
        if name == "replace":
            return _fn_replace(values, self._path)
        if name == "split":
            return _fn_split(values, self._path)
        return _fail(
            self._path,
            "unknown_function",
            "unknown_function",
            {"name": name},
        )


def _compare_num(op: str, left: int | float, right: int | float) -> bool:
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    return left >= right


def _compare_str(op: str, left: str, right: str) -> bool:
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    return left >= right


def _eval_in(*, left: Any, right: Any, path: str) -> EvalResult:
    if isinstance(right, str):
        if isinstance(left, str):
            return True, left in right, None
        return _fail(path, "type_mismatch", "string_membership_requires_string")
    if isinstance(right, list):
        return True, left in right, None
    if isinstance(right, dict):
        if not isinstance(left, Hashable):
            return _fail(
                path,
                "type_mismatch",
                "dict_membership_requires_hashable_key",
            )
        return True, left in right, None
    return _fail(path, "type_mismatch", "in_requires_string_list_or_object")


def _expect_arity(args: list[Any], count: int, *, name: str, path: str) -> ExprEvalError | None:
    if len(args) == count:
        return None
    return _error(
        code="type_mismatch",
        path=path,
        reason="invalid_arity",
        meta={"name": name, "expected": count, "actual": len(args)},
    )


def _fn_len(args: list[Any], path: str) -> EvalResult:
    err = _expect_arity(args, 1, name="len", path=path)
    if err is not None:
        return False, None, err
    value = args[0]
    if isinstance(value, (str, list, dict)):
        return True, len(value), None
    return _fail(
        path,
        "type_mismatch",
        "len_requires_string_list_or_object",
        {"type": type(value).__name__},
    )


def _fn_bool_list(name: str, args: list[Any], path: str) -> EvalResult:
    err = _expect_arity(args, 1, name=name, path=path)
    if err is not None:
        return False, None, err
    value = args[0]
    if not isinstance(value, list):
        return _fail(
            path,
            "type_mismatch",
            f"{name}_requires_list",
            {"type": type(value).__name__},
        )
    if not all(isinstance(item, bool) for item in value):
        return _fail(path, "type_mismatch", f"{name}_requires_bool_items")
    return True, any(value) if name == "any" else all(value), None


def _fn_case(name: str, args: list[Any], path: str) -> EvalResult:
    err = _expect_arity(args, 1, name=name, path=path)
    if err is not None:
        return False, None, err
    value = args[0]
    if not isinstance(value, str):
        return _fail(
            path,
            "type_mismatch",
            f"{name}_requires_string",
            {"type": type(value).__name__},
        )
    return True, value.lower() if name == "lower" else value.upper(), None


def _fn_replace(args: list[Any], path: str) -> EvalResult:
    err = _expect_arity(args, 3, name="replace", path=path)
    if err is not None:
        return False, None, err
    value, old, new = args
    if isinstance(value, str) and isinstance(old, str) and isinstance(new, str):
        return True, value.replace(old, new), None
    return _fail(path, "type_mismatch", "replace_requires_strings")


def _fn_split(args: list[Any], path: str) -> EvalResult:
    err = _expect_arity(args, 2, name="split", path=path)
    if err is not None:
        return False, None, err
    value, sep = args
    if isinstance(value, str) and isinstance(sep, str):
        return True, value.split(sep), None
    return _fail(path, "type_mismatch", "split_requires_strings")


def eval_expr_ref(
    expr_ref: Any,
    *,
    state: Any,
    inputs: Any,
    op_outputs: Any = None,
    allow_op_outputs: bool = False,
    path: str = "$",
) -> tuple[bool, Any | None, dict[str, Any] | None]:
    """Evaluate an ExprRef with total semantics and structured failures."""

    expr_path = f"{path}.expr"
    try:
        if not _is_expr_ref(expr_ref):
            error = _error(
                code="invalid_expr_ref",
                path=path,
                reason="invalid_expr_ref",
            )
            return False, None, _to_error_obj(error)
        ok, ast, parse_error = parse_expr(expr_ref["expr"], path=expr_path)
        if not ok or ast is None:
            err: ErrorLike = parse_error or _error(
                code="internal_error",
                path=expr_path,
                reason="parse_failed",
            )
            return False, None, _to_error_obj(err)
        ok, value, eval_error = _Evaluator(
            state=state,
            inputs=inputs,
            op_outputs=op_outputs,
            allow_op_outputs=allow_op_outputs,
            path=expr_path,
        ).eval(ast)
        if not ok:
            err = eval_error or _error(
                code="internal_error",
                path=expr_path,
                reason="eval_failed",
            )
            return False, None, _to_error_obj(err)
        return True, value, None
    except Exception as exc:  # pragma: no cover
        return (
            False,
            None,
            _to_error_obj(
                _error(
                    code="internal_error",
                    path=expr_path,
                    reason="unexpected_exception",
                    meta={"type": type(exc).__name__},
                )
            ),
        )
