"""Parser for the sealed ExprRef baseline language.

ASCII-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .expr_tokens import ExprToken, ExprTokenError, tokenize_expr


@dataclass(frozen=True)
class LiteralNode:
    value: Any


@dataclass(frozen=True)
class PathNode:
    root: tuple[str, ...]
    segments: tuple[str | int, ...]


@dataclass(frozen=True)
class UnaryOpNode:
    op: str
    operand: Any


@dataclass(frozen=True)
class BinaryOpNode:
    op: str
    left: Any
    right: Any


@dataclass(frozen=True)
class CallNode:
    name: str
    args: tuple[Any, ...]


ExprAst = LiteralNode | PathNode | UnaryOpNode | BinaryOpNode | CallNode


@dataclass(frozen=True)
class ExprParseError:
    code: str
    path: str
    reason: str
    meta: dict[str, Any]


def _error(
    *,
    code: str,
    path: str,
    reason: str,
    meta: dict[str, Any] | None = None,
) -> ExprParseError:
    return ExprParseError(
        code=code,
        path=path,
        reason=reason,
        meta={} if meta is None else dict(meta),
    )


class _Parser:
    def __init__(self, tokens: list[ExprToken], *, path: str) -> None:
        self._tokens = tokens
        self._path = path
        self._idx = 0

    def parse(self) -> tuple[bool, ExprAst | None, ExprParseError | None]:
        node = self._parse_or()
        if isinstance(node, ExprParseError):
            return False, None, node
        end = self._peek()
        if end.kind != "EOF":
            return (
                False,
                None,
                _error(
                    code="invalid_expr_syntax",
                    path=self._path,
                    reason="unexpected_token",
                    meta={"offset": end.start, "token": end.kind},
                ),
            )
        return True, node, None

    def _peek(self) -> ExprToken:
        return self._tokens[self._idx]

    def _advance(self) -> ExprToken:
        token = self._tokens[self._idx]
        self._idx += 1
        return token

    def _match(self, kind: str, value: Any | None = None) -> ExprToken | None:
        token = self._peek()
        if token.kind != kind:
            return None
        if value is not None and token.value != value:
            return None
        return self._advance()

    def _parse_or(self) -> ExprAst | ExprParseError:
        left = self._parse_and()
        if isinstance(left, ExprParseError):
            return left
        while self._match("OP", "or") is not None:
            right = self._parse_and()
            if isinstance(right, ExprParseError):
                return right
            left = BinaryOpNode(op="or", left=left, right=right)
        return left

    def _parse_and(self) -> ExprAst | ExprParseError:
        left = self._parse_not()
        if isinstance(left, ExprParseError):
            return left
        while self._match("OP", "and") is not None:
            right = self._parse_not()
            if isinstance(right, ExprParseError):
                return right
            left = BinaryOpNode(op="and", left=left, right=right)
        return left

    def _parse_not(self) -> ExprAst | ExprParseError:
        if self._match("OP", "not") is not None:
            operand = self._parse_not()
            if isinstance(operand, ExprParseError):
                return operand
            return UnaryOpNode(op="not", operand=operand)
        return self._parse_compare()

    def _parse_compare(self) -> ExprAst | ExprParseError:
        left = self._parse_primary()
        if isinstance(left, ExprParseError):
            return left
        token = self._peek()
        if token.kind == "OP" and token.value in {
            "==",
            "!=",
            "<",
            "<=",
            ">",
            ">=",
            "in",
        }:
            op = self._advance().value
            right = self._parse_primary()
            if isinstance(right, ExprParseError):
                return right
            return BinaryOpNode(op=op, left=left, right=right)
        return left

    def _parse_primary(self) -> ExprAst | ExprParseError:
        token = self._peek()
        if token.kind in {"STRING", "NUMBER", "BOOLEAN", "NULL"}:
            self._advance()
            return LiteralNode(value=token.value)
        if token.kind == "IDENT":
            return self._parse_ident_expr()
        if token.kind == "DOLLAR":
            return self._parse_path()
        if self._match("LPAREN") is not None:
            node = self._parse_or()
            if isinstance(node, ExprParseError):
                return node
            if self._match("RPAREN") is None:
                end = self._peek()
                return _error(
                    code="invalid_expr_syntax",
                    path=self._path,
                    reason="missing_rparen",
                    meta={"offset": end.start},
                )
            return node
        return _error(
            code="invalid_expr_syntax",
            path=self._path,
            reason="unexpected_token",
            meta={"offset": token.start, "token": token.kind},
        )

    def _parse_ident_expr(self) -> ExprAst | ExprParseError:
        ident = self._advance()
        if self._match("LPAREN") is None:
            return _error(
                code="invalid_expr_syntax",
                path=self._path,
                reason="bare_identifier",
                meta={"offset": ident.start, "value": ident.value},
            )
        args: list[ExprAst] = []
        if self._match("RPAREN") is not None:
            return CallNode(name=str(ident.value), args=tuple(args))
        while True:
            arg = self._parse_or()
            if isinstance(arg, ExprParseError):
                return arg
            args.append(arg)
            if self._match("COMMA") is not None:
                continue
            if self._match("RPAREN") is not None:
                break
            token = self._peek()
            return _error(
                code="invalid_expr_syntax",
                path=self._path,
                reason="missing_comma_or_rparen",
                meta={"offset": token.start},
            )
        return CallNode(name=str(ident.value), args=tuple(args))

    def _parse_path(self) -> ExprAst | ExprParseError:
        self._advance()
        if self._match("DOT") is None:
            token = self._peek()
            return _error(
                code="invalid_expr_syntax",
                path=self._path,
                reason="invalid_root",
                meta={"offset": token.start},
            )
        root_first = self._match("IDENT")
        if root_first is None:
            token = self._peek()
            return _error(
                code="invalid_expr_syntax",
                path=self._path,
                reason="invalid_root",
                meta={"offset": token.start},
            )
        root: list[str] = [str(root_first.value)]
        if root[0] == "op":
            if self._match("DOT") is None:
                token = self._peek()
                return _error(
                    code="invalid_expr_syntax",
                    path=self._path,
                    reason="invalid_root",
                    meta={"offset": token.start},
                )
            second = self._match("IDENT")
            if second is None:
                token = self._peek()
                return _error(
                    code="invalid_expr_syntax",
                    path=self._path,
                    reason="invalid_root",
                    meta={"offset": token.start},
                )
            root.append(str(second.value))

        segments: list[str | int] = []
        while True:
            if self._match("DOT") is not None:
                ident = self._match("IDENT")
                if ident is None:
                    token = self._peek()
                    return _error(
                        code="invalid_expr_syntax",
                        path=self._path,
                        reason="expected_path_segment",
                        meta={"offset": token.start},
                    )
                segments.append(str(ident.value))
                continue
            if self._match("LBRACKET") is not None:
                item = self._peek()
                if item.kind == "STRING":
                    segments.append(str(self._advance().value))
                elif item.kind == "NUMBER" and isinstance(item.value, int):
                    segments.append(int(self._advance().value))
                else:
                    return _error(
                        code="invalid_expr_syntax",
                        path=self._path,
                        reason="invalid_bracket_segment",
                        meta={"offset": item.start},
                    )
                if self._match("RBRACKET") is None:
                    token = self._peek()
                    return _error(
                        code="invalid_expr_syntax",
                        path=self._path,
                        reason="missing_rbracket",
                        meta={"offset": token.start},
                    )
                continue
            break
        return PathNode(root=tuple(root), segments=tuple(segments))


def _from_token_error(error: ExprTokenError) -> ExprParseError:
    return ExprParseError(
        code=error.code,
        path=error.path,
        reason=error.reason,
        meta=dict(error.meta),
    )


def parse_expr(
    expr: str, *, path: str = "$.expr"
) -> tuple[
    bool,
    ExprAst | None,
    ExprParseError | None,
]:
    """Parse a baseline ExprRef expression into a small AST."""

    try:
        ok, tokens, error = tokenize_expr(expr, path=path)
        if not ok or tokens is None:
            token_error = error or ExprTokenError(
                code="internal_error",
                path=path,
                reason="tokenize_failed",
                meta={},
            )
            return False, None, _from_token_error(token_error)
        parser = _Parser(tokens, path=path)
        return parser.parse()
    except Exception as exc:
        return (
            False,
            None,
            _error(
                code="internal_error",
                path=path,
                reason="unexpected_parse_exception",
                meta={
                    "exception_type": type(exc).__name__,
                    "message": str(exc),
                },
            ),
        )
