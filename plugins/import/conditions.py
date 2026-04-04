"""Condition evaluation for wizard FlowGraph transitions.

The condition language is intentionally small and deterministic.

Supported forms:

- True / False (bool): returned directly.
- None: treated as True.
- dict with "op":
  - {"op": "eq", "path": "inputs.step.field", "value": X}
  - {"op": "ne", "path": "...", "value": X}
  - {"op": "exists", "path": "..."}
  - {"op": "truthy", "path": "..."}
  - {"op": "and", "conds": [cond, ...]}
  - {"op": "or", "conds": [cond, ...]}
  - {"op": "not", "cond": cond}

Compatibility forms (dict):
- {"path": "...", "equals": X}  (same as eq)
- {"path": "...", "not_equals": X} (same as ne)

Paths are resolved against a state view object with keys:
- "inputs": state["inputs"]
- "state": a state subset (engine-owned)

ASCII-only.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from .flow_graph_state_view import FlowGraphStateView


def eval_condition(
    cond: Any,
    state_view: FlowGraphStateView,
    *,
    warn: Callable[[str, dict[str, Any]], None] | None = None,
) -> bool:
    if cond is None:
        return True
    if isinstance(cond, bool):
        return cond
    if isinstance(cond, dict):
        op_any = cond.get("op")
        if op_any is None:
            # Compatibility forms
            if "path" in cond and "equals" in cond:
                return _op_eq(cond, state_view, warn=warn)
            if "path" in cond and "not_equals" in cond:
                return _op_ne(cond, state_view, warn=warn)
            return False

        op = str(op_any)
        if op == "eq":
            return _op_eq(cond, state_view, warn=warn)
        if op == "ne":
            return _op_ne(cond, state_view, warn=warn)
        if op == "exists":
            return _op_exists(cond, state_view, warn=warn)
        if op == "truthy":
            return _op_truthy(cond, state_view, warn=warn)
        if op == "and":
            conds_any = cond.get("conds")
            if not isinstance(conds_any, list):
                return False
            return all(eval_condition(c, state_view, warn=warn) for c in conds_any)
        if op == "or":
            conds_any = cond.get("conds")
            if not isinstance(conds_any, list):
                return False
            return any(eval_condition(c, state_view, warn=warn) for c in conds_any)
        if op == "not":
            return not eval_condition(cond.get("cond"), state_view, warn=warn)
        return False
    return False


def _op_eq(
    cond: dict[str, Any],
    state_view: FlowGraphStateView,
    *,
    warn: Callable[[str, dict[str, Any]], None] | None = None,
) -> bool:
    path = cond.get("path")
    if not isinstance(path, str) or not path:
        return False
    expected = cond.get("value", cond.get("equals"))
    actual = _get_path(state_view, path, warn=warn)
    return actual == expected


def _op_ne(
    cond: dict[str, Any],
    state_view: FlowGraphStateView,
    *,
    warn: Callable[[str, dict[str, Any]], None] | None = None,
) -> bool:
    path = cond.get("path")
    if not isinstance(path, str) or not path:
        return False
    expected = cond.get("value", cond.get("not_equals"))
    actual = _get_path(state_view, path, warn=warn)
    return actual != expected


def _op_exists(
    cond: dict[str, Any],
    state_view: FlowGraphStateView,
    *,
    warn: Callable[[str, dict[str, Any]], None] | None = None,
) -> bool:
    path = cond.get("path")
    if not isinstance(path, str) or not path:
        return False
    marker = object()
    return _get_path(state_view, path, default=marker, warn=warn) is not marker


def _op_truthy(
    cond: dict[str, Any],
    state_view: FlowGraphStateView,
    *,
    warn: Callable[[str, dict[str, Any]], None] | None = None,
) -> bool:
    path = cond.get("path")
    if not isinstance(path, str) or not path:
        return False
    return bool(_get_path(state_view, path, warn=warn))


_PART_RE = re.compile(r"^(?P<key>[^\[]+)(\[(?P<idx>\d+)\])?$")


def find_invalid_condition_path(cond: Any) -> str | None:
    """Return the first invalid path found in a condition tree, or None."""

    def _walk(c: Any) -> str | None:
        if c is None or isinstance(c, bool):
            return None
        if not isinstance(c, dict):
            return None

        op = c.get("op")
        if op in {"and", "or"}:
            conds_any = c.get("conds")
            if not isinstance(conds_any, list):
                return None
            for x in conds_any:
                bad = _walk(x)
                if bad is not None:
                    return bad
            return None
        if op == "not":
            return _walk(c.get("cond"))

        path = c.get("path")
        if isinstance(path, str) and path and not _is_valid_path_prefix(path):
            return path
        return None

    return _walk(cond)


def _is_valid_path_prefix(path: str) -> bool:
    return path.startswith("$.inputs.") or path.startswith("$.state.")


def _normalize_runtime_path(path: str) -> str | None:
    if path.startswith("$."):
        return path[2:]
    return None


def _get_path(
    obj: Any,
    path: str,
    *,
    default: Any = None,
    warn: Callable[[str, dict[str, Any]], None] | None = None,
) -> Any:
    runtime_path = _normalize_runtime_path(path)
    if runtime_path is None:
        if warn is not None:
            warn("INVALID_CONDITION_PATH", {"path": path})
        return default

    cur = obj
    for raw_part in runtime_path.split("."):
        part = raw_part.strip()
        if not part:
            return default
        m = _PART_RE.match(part)
        if not m:
            return default
        key = m.group("key")
        idx_s = m.group("idx")

        if isinstance(cur, dict):
            if key not in cur:
                return default
            cur = cur[key]
        else:
            return default

        if idx_s is not None:
            if not isinstance(cur, list):
                return default
            idx = int(idx_s)
            if idx < 0 or idx >= len(cur):
                return default
            cur = cur[idx]
    return cur
