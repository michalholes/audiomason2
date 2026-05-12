"""Tests for arithmetic operators and indexing in the ExprRef evaluator.

Covers:
- Binary arithmetic: +, -, *, /, //, %
- Operator precedence (* before +, etc.)
- Parentheses override precedence
- Unary minus via negative literals
- Postfix indexing: expr[n] (list) and expr[key] (dict)
- Error cases: type mismatch, division by zero, out-of-range index
"""

from __future__ import annotations

from importlib import import_module

import pytest

_dsl = import_module("plugins.import.dsl")
eval_expr_ref = _dsl.eval_expr_ref
_parser = import_module("plugins.import.dsl.expr_parser")
parse_expr = _parser.parse_expr
BinaryOpNode = _parser.BinaryOpNode
IndexNode = _parser.IndexNode
LiteralNode = _parser.LiteralNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _eval(expr: str, *, state: object = None, inputs: object = None) -> tuple:
    return eval_expr_ref(
        {"expr": expr},
        state=state or {},
        inputs=inputs or {},
    )


# ---------------------------------------------------------------------------
# Parser: operator precedence
# ---------------------------------------------------------------------------

class TestParserPrecedence:
    def test_mul_binds_tighter_than_add(self) -> None:
        # 1 + 2 * 3  =>  1 + (2 * 3)
        ok, ast, err = parse_expr("1 + 2 * 3")
        assert ok and err is None
        assert isinstance(ast, BinaryOpNode) and ast.op == "+"
        assert isinstance(ast.right, BinaryOpNode) and ast.right.op == "*"

    def test_parens_override_precedence(self) -> None:
        # (1 + 2) * 3  =>  (1 + 2) * 3
        ok, ast, err = parse_expr("(1 + 2) * 3")
        assert ok and err is None
        assert isinstance(ast, BinaryOpNode) and ast.op == "*"
        assert isinstance(ast.left, BinaryOpNode) and ast.left.op == "+"

    def test_floordiv_same_level_as_mul(self) -> None:
        ok, ast, err = parse_expr("6 // 2 * 3")
        assert ok and err is None
        # Left-associative: (6 // 2) * 3
        assert isinstance(ast, BinaryOpNode) and ast.op == "*"
        assert isinstance(ast.left, BinaryOpNode) and ast.left.op == "//"

    def test_subtraction_left_associative(self) -> None:
        ok, ast, err = parse_expr("10 - 3 - 2")
        assert ok and err is None
        # (10 - 3) - 2
        assert isinstance(ast, BinaryOpNode) and ast.op == "-"
        assert isinstance(ast.left, BinaryOpNode) and ast.left.op == "-"

    def test_index_produces_index_node_on_call(self) -> None:
        ok, ast, err = parse_expr('split("a,b", ",")[0]')
        assert ok and err is None
        assert isinstance(ast, IndexNode)
        assert isinstance(ast.index, LiteralNode) and ast.index.value == 0


# ---------------------------------------------------------------------------
# Evaluator: basic arithmetic
# ---------------------------------------------------------------------------

class TestArithEval:
    @pytest.mark.parametrize(
        ("expr", "expected"),
        [
            ("1 + 2", 3),
            ("5 - 3", 2),
            ("2 * 3", 6),
            ("10 / 2", 5.0),
            ("10 // 3", 3),
            ("10 % 3", 1),
            ("7 % 3", 1),
            ("0 + 0", 0),
        ],
    )
    def test_basic_ops(self, expr: str, expected: object) -> None:
        ok, value, err = _eval(expr)
        assert ok is True and err is None
        assert value == expected

    def test_operator_precedence_mul_before_add(self) -> None:
        ok, value, err = _eval("1 + 2 * 3")
        assert ok is True and value == 7

    def test_parens_override(self) -> None:
        ok, value, err = _eval("(1 + 2) * 3")
        assert ok is True and value == 9

    def test_chained_ops_left_associative(self) -> None:
        ok, value, err = _eval("10 - 3 - 2")
        assert ok is True and value == 5

    def test_nested_arithmetic(self) -> None:
        ok, value, err = _eval("2 * (3 + 4) - 1")
        assert ok is True and value == 13

    def test_floordiv(self) -> None:
        ok, value, err = _eval("7 // 2")
        assert ok is True and value == 3

    def test_modulo(self) -> None:
        ok, value, err = _eval("7 % 4")
        assert ok is True and value == 3

    def test_float_arithmetic(self) -> None:
        ok, value, err = _eval("1.5 + 0.5")
        assert ok is True
        assert abs(value - 2.0) < 1e-9

    def test_string_concatenation_with_plus(self) -> None:
        ok, value, err = _eval('"hello" + " world"')
        assert ok is True and value == "hello world"

    def test_negative_literal(self) -> None:
        ok, value, err = _eval("-5 + 3")
        assert ok is True and value == -2


# ---------------------------------------------------------------------------
# Evaluator: arithmetic with path references
# ---------------------------------------------------------------------------

class TestArithWithPaths:
    def test_add_path_and_literal(self) -> None:
        ok, value, err = _eval(
            "$.state.count + 5",
            state={"count": 10},
        )
        assert ok is True and value == 15

    def test_mul_two_paths(self) -> None:
        ok, value, err = _eval(
            "$.inputs.x * $.inputs.y",
            inputs={"x": 4, "y": 3},
        )
        assert ok is True and value == 12

    def test_arith_in_comparison(self) -> None:
        ok, value, err = _eval(
            "$.state.count + 5 > 10",
            state={"count": 6},
        )
        assert ok is True and value is True

    def test_arith_combined_with_boolean(self) -> None:
        ok, value, err = _eval(
            "$.state.a + $.state.b == 7 and $.state.c == true",
            state={"a": 3, "b": 4, "c": True},
        )
        assert ok is True and value is True


# ---------------------------------------------------------------------------
# Evaluator: postfix indexing
# ---------------------------------------------------------------------------

class TestIndexEval:
    def test_list_index_zero(self) -> None:
        ok, value, err = _eval('split("a,b,c", ",")[0]')
        assert ok is True and value == "a"

    def test_list_index_nonzero(self) -> None:
        ok, value, err = _eval('split("a,b,c", ",")[2]')
        assert ok is True and value == "c"

    def test_list_index_via_path(self) -> None:
        ok, value, err = _eval(
            "$.inputs.items[1]",
            inputs={"items": [10, 20, 30]},
        )
        assert ok is True and value == 20

    def test_dict_key_index_via_path(self) -> None:
        ok, value, err = _eval(
            '$.inputs.data["key"]',
            inputs={"data": {"key": "found"}},
        )
        assert ok is True and value == "found"

    def test_nested_index(self) -> None:
        # split returns list; index into it
        ok, value, err = _eval('split("x:y:z", ":")[1]')
        assert ok is True and value == "y"

    def test_index_result_used_in_comparison(self) -> None:
        ok, value, err = _eval(
            'split("a,b,c", ",")[0] == "a"'
        )
        assert ok is True and value is True

    def test_index_result_in_arithmetic(self) -> None:
        ok, value, err = _eval(
            "$.inputs.nums[0] + $.inputs.nums[1]",
            inputs={"nums": [3, 7]},
        )
        assert ok is True and value == 10


# ---------------------------------------------------------------------------
# Evaluator: error cases
# ---------------------------------------------------------------------------

class TestArithErrors:
    def test_type_mismatch_string_plus_number(self) -> None:
        ok, value, err = _eval('"a" + 1')
        assert ok is False and err is not None
        assert err["code"] == "type_mismatch"
        assert err["reason"] == "arithmetic_requires_numbers"

    def test_type_mismatch_bool_in_arithmetic(self) -> None:
        ok, value, err = _eval("true + 1")
        assert ok is False and err is not None
        assert err["code"] == "type_mismatch"

    def test_division_by_zero(self) -> None:
        ok, value, err = _eval("5 / 0")
        assert ok is False and err is not None
        assert err["code"] == "arithmetic_error"
        assert err["reason"] == "division_by_zero"

    def test_floordiv_by_zero(self) -> None:
        ok, value, err = _eval("5 // 0")
        assert ok is False and err is not None
        assert err["code"] == "arithmetic_error"
        assert err["reason"] == "division_by_zero"

    def test_modulo_by_zero(self) -> None:
        ok, value, err = _eval("5 % 0")
        assert ok is False and err is not None
        assert err["code"] == "arithmetic_error"
        assert err["reason"] == "division_by_zero"

    def test_list_index_out_of_range(self) -> None:
        ok, value, err = _eval('split("a,b", ",")[5]')
        assert ok is False and err is not None
        assert err["code"] == "missing_path"
        assert err["reason"] == "list_index_out_of_range"

    def test_list_index_string_key_rejected(self) -> None:
        ok, value, err = _eval('split("a,b", ",")["key"]')
        assert ok is False and err is not None
        assert err["code"] == "type_mismatch"
        assert err["reason"] == "list_index_requires_int"

    def test_dict_index_missing_key(self) -> None:
        # PathNode handles $.inputs.data["key"] directly; missing key
        ok, value, err = _eval(
            '$.inputs.data["missing"]',
            inputs={"data": {"key": "val"}},
        )
        assert ok is False and err is not None
        assert err["code"] == "missing_path"

    def test_index_on_non_collection(self) -> None:
        # PathNode handles $.inputs.num[0]; num is not a list -> path access error
        ok, value, err = _eval(
            "$.inputs.num[0]",
            inputs={"num": 42},
        )
        assert ok is False and err is not None
        # PathNode reports invalid_path_access when value is not a list
        assert err["code"] in {"type_mismatch", "invalid_path_access"}

    def test_index_on_non_collection_via_index_node(self) -> None:
        # IndexNode on a non-collection (use expression form, not path form)
        # split() returns list, but if we construct a non-collection target via arithmetic:
        # 5[0] - parse this; 5 is a literal and [0] should give IndexNode
        ok, value, err = _eval("(1 + 1)[0]")
        assert ok is False and err is not None
        assert err["code"] == "type_mismatch"
        assert err["reason"] == "index_requires_list_or_dict"


# ---------------------------------------------------------------------------
# Tokenizer: ensure '-' is handled correctly in context
# ---------------------------------------------------------------------------

class TestTokenizerMinus:
    def test_binary_minus_after_number(self) -> None:
        tokenize_expr = import_module("plugins.import.dsl.expr_tokens").tokenize_expr

        ok, tokens, err = tokenize_expr("5 - 3")
        assert ok is True
        kinds = [(t.kind, t.value) for t in tokens if t.kind != "EOF"]
        assert kinds == [("NUMBER", 5), ("OP", "-"), ("NUMBER", 3)]

    def test_unary_minus_at_start(self) -> None:
        tokenize_expr = import_module("plugins.import.dsl.expr_tokens").tokenize_expr

        ok, tokens, err = tokenize_expr("-5")
        assert ok is True
        kinds = [(t.kind, t.value) for t in tokens if t.kind != "EOF"]
        assert kinds == [("NUMBER", -5)]

    def test_binary_minus_after_paren(self) -> None:
        tokenize_expr = import_module("plugins.import.dsl.expr_tokens").tokenize_expr

        ok, tokens, err = tokenize_expr("(1 + 2) - 1")
        assert ok is True
        kinds = [t.kind for t in tokens if t.kind != "EOF"]
        # LPAREN NUMBER OP NUMBER RPAREN OP NUMBER
        assert kinds == ["LPAREN", "NUMBER", "OP", "NUMBER", "RPAREN", "OP", "NUMBER"]
