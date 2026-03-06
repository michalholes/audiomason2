"""Issue 103: ExprRef parser behavior."""

from __future__ import annotations

from importlib import import_module

parse_expr = import_module("plugins.import.dsl.expr_parser").parse_expr
PathNode = import_module("plugins.import.dsl.expr_parser").PathNode
BinaryOpNode = import_module("plugins.import.dsl.expr_parser").BinaryOpNode
CallNode = import_module("plugins.import.dsl.expr_parser").CallNode


def test_parse_expr_builds_ast_for_boolean_compare() -> None:
    ok, ast, error = parse_expr("len($.inputs.items) >= 2 and $.state.enabled == true")

    assert ok is True
    assert error is None
    assert isinstance(ast, BinaryOpNode)
    assert ast.op == "and"
    assert isinstance(ast.left, BinaryOpNode)
    assert ast.left.op == ">="
    assert isinstance(ast.left.left, CallNode)
    assert ast.left.left.name == "len"
    assert isinstance(ast.left.left.args[0], PathNode)


def test_parse_expr_rejects_bad_syntax() -> None:
    ok, ast, error = parse_expr("len($.inputs.items) >=")

    assert ok is False
    assert ast is None
    assert error is not None
    assert error.code == "invalid_expr_syntax"
    assert error.reason == "unexpected_token"


def test_parse_expr_rejects_unsupported_token() -> None:
    ok, ast, error = parse_expr('$.inputs.name @ "x"')

    assert ok is False
    assert ast is None
    assert error is not None
    assert error.code == "invalid_expr_syntax"
    assert error.reason == "unsupported_character"
