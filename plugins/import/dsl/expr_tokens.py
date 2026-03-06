"""Tokenizer for the sealed ExprRef baseline language.

ASCII-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExprToken:
    """Single lexical token."""

    kind: str
    value: Any
    start: int
    end: int


@dataclass(frozen=True)
class ExprTokenError:
    """Structured tokenizer error."""

    code: str
    path: str
    reason: str
    meta: dict[str, Any]


_KEYWORDS = {
    "and": "OP",
    "or": "OP",
    "not": "OP",
    "in": "OP",
    "true": "BOOLEAN",
    "false": "BOOLEAN",
    "null": "NULL",
}

_DOUBLE_OPS = {"==", "!=", "<=", ">="}
_SINGLE_OPS = {"<", ">"}


def _error(
    *,
    code: str,
    path: str,
    reason: str,
    meta: dict[str, Any] | None = None,
) -> ExprTokenError:
    return ExprTokenError(
        code=code,
        path=path,
        reason=reason,
        meta={} if meta is None else dict(meta),
    )


def _read_string(
    expr: str,
    *,
    pos: int,
    path: str,
) -> tuple[bool, str | None, int, ExprTokenError | None]:
    quote = expr[pos]
    chars: list[str] = []
    idx = pos + 1
    escapes = {
        "\\": "\\",
        '"': '"',
        "'": "'",
        "n": "\n",
        "r": "\r",
        "t": "\t",
    }
    while idx < len(expr):
        ch = expr[idx]
        if ch == quote:
            return True, "".join(chars), idx + 1, None
        if ch == "\\":
            nxt = idx + 1
            if nxt >= len(expr):
                return (
                    False,
                    None,
                    idx,
                    _error(
                        code="invalid_expr_syntax",
                        path=path,
                        reason="unterminated_string",
                        meta={"offset": pos},
                    ),
                )
            esc = expr[nxt]
            if esc not in escapes:
                return (
                    False,
                    None,
                    idx,
                    _error(
                        code="invalid_expr_syntax",
                        path=path,
                        reason="invalid_escape",
                        meta={"offset": nxt, "value": esc},
                    ),
                )
            chars.append(escapes[esc])
            idx += 2
            continue
        chars.append(ch)
        idx += 1
    return (
        False,
        None,
        idx,
        _error(
            code="invalid_expr_syntax",
            path=path,
            reason="unterminated_string",
            meta={"offset": pos},
        ),
    )


def _read_number(
    expr: str,
    *,
    pos: int,
    path: str,
) -> tuple[bool, int | float | None, int, ExprTokenError | None]:
    idx = pos
    if expr[idx] == "-":
        idx += 1
    start = idx
    while idx < len(expr) and expr[idx].isdigit():
        idx += 1
    if idx < len(expr) and expr[idx] == ".":
        idx += 1
        frac_start = idx
        while idx < len(expr) and expr[idx].isdigit():
            idx += 1
        if frac_start == idx:
            return (
                False,
                None,
                idx,
                _error(
                    code="invalid_expr_syntax",
                    path=path,
                    reason="invalid_number",
                    meta={"offset": pos},
                ),
            )
    if start == idx:
        return (
            False,
            None,
            idx,
            _error(
                code="invalid_expr_syntax",
                path=path,
                reason="invalid_number",
                meta={"offset": pos},
            ),
        )
    raw = expr[pos:idx]
    value: int | float
    value = float(raw) if "." in raw else int(raw)
    return True, value, idx, None


def _read_ident(expr: str, *, pos: int) -> tuple[str, int]:
    idx = pos
    while idx < len(expr) and (expr[idx].isalnum() or expr[idx] == "_"):
        idx += 1
    return expr[pos:idx], idx


def tokenize_expr(
    expr: str, *, path: str = "$.expr"
) -> tuple[
    bool,
    list[ExprToken] | None,
    ExprTokenError | None,
]:
    """Tokenize a baseline ExprRef expression."""

    if not isinstance(expr, str):
        return (
            False,
            None,
            _error(
                code="invalid_expr_syntax",
                path=path,
                reason="expr_not_string",
                meta={},
            ),
        )

    tokens: list[ExprToken] = []
    idx = 0
    while idx < len(expr):
        ch = expr[idx]
        if ch.isspace():
            idx += 1
            continue

        two = expr[idx : idx + 2]
        if two in _DOUBLE_OPS:
            tokens.append(ExprToken(kind="OP", value=two, start=idx, end=idx + 2))
            idx += 2
            continue

        if ch in _SINGLE_OPS:
            tokens.append(ExprToken(kind="OP", value=ch, start=idx, end=idx + 1))
            idx += 1
            continue

        if ch in {'"', "'"}:
            ok, string_value, nxt, err = _read_string(expr, pos=idx, path=path)
            if not ok:
                return False, None, err
            tokens.append(ExprToken(kind="STRING", value=string_value, start=idx, end=nxt))
            idx = nxt
            continue

        if ch.isdigit() or (ch == "-" and idx + 1 < len(expr) and expr[idx + 1].isdigit()):
            ok, number_value, nxt, err = _read_number(expr, pos=idx, path=path)
            if not ok:
                return False, None, err
            tokens.append(ExprToken(kind="NUMBER", value=number_value, start=idx, end=nxt))
            idx = nxt
            continue

        if ch.isalpha() or ch == "_":
            ident, nxt = _read_ident(expr, pos=idx)
            kind = _KEYWORDS.get(ident, "IDENT")
            token_value: Any = ident
            if ident == "true":
                token_value = True
            elif ident == "false":
                token_value = False
            elif ident == "null":
                token_value = None
            tokens.append(ExprToken(kind=kind, value=token_value, start=idx, end=nxt))
            idx = nxt
            continue

        if ch == "$":
            tokens.append(ExprToken(kind="DOLLAR", value=ch, start=idx, end=idx + 1))
            idx += 1
            continue
        if ch == ".":
            tokens.append(ExprToken(kind="DOT", value=ch, start=idx, end=idx + 1))
            idx += 1
            continue
        if ch == "(":
            tokens.append(ExprToken(kind="LPAREN", value=ch, start=idx, end=idx + 1))
            idx += 1
            continue
        if ch == ")":
            tokens.append(ExprToken(kind="RPAREN", value=ch, start=idx, end=idx + 1))
            idx += 1
            continue
        if ch == ",":
            tokens.append(ExprToken(kind="COMMA", value=ch, start=idx, end=idx + 1))
            idx += 1
            continue
        if ch == "[":
            tokens.append(ExprToken(kind="LBRACKET", value=ch, start=idx, end=idx + 1))
            idx += 1
            continue
        if ch == "]":
            tokens.append(ExprToken(kind="RBRACKET", value=ch, start=idx, end=idx + 1))
            idx += 1
            continue

        return (
            False,
            None,
            _error(
                code="invalid_expr_syntax",
                path=path,
                reason="unsupported_character",
                meta={"offset": idx, "value": ch},
            ),
        )

    tokens.append(ExprToken(kind="EOF", value=None, start=len(expr), end=len(expr)))
    return True, tokens, None
