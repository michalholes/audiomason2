"""FlowConfig patch mode for POST /import/ui/config.

Patch mode is a UI-facing wrapper that applies a deterministic set of
operations to the currently persisted FlowConfig.

This module is intentionally isolated to avoid monolith growth.

ASCII-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeGuard

from plugins.file_io.service import FileService
from plugins.file_io.service.types import RootName

from .defaults import ensure_default_models
from .errors import validation_error
from .storage import atomic_write_json, read_json


class _PatchEngine(Protocol):
    _fs: FileService

    def _normalize_flow_config(self, raw: object) -> dict[str, object]: ...

    def validate_flow_config(self, flow_config_json: object) -> dict[str, object]: ...


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


@dataclass(frozen=True)
class PatchOp:
    op: str
    path: str
    value: object


def apply_patch_request(engine: _PatchEngine, body: object) -> dict[str, object] | None:
    """Handle patch wrapper if present.

    Returns:
      - None if body is not a patch wrapper.
      - FlowConfig dict or error envelope dict.
    """

    if not _is_str_object_dict(body):
        return None
    if body.get("mode") != "patch":
        return None

    ops_any = body.get("ops")
    if not _is_object_list(ops_any) or not ops_any:
        return _patch_validation_error(
            index=None,
            path="$.ops",
            reason="invalid_ops",
            message="patch ops must be a non-empty list",
            meta={"expected": "non-empty list"},
        )

    ops: list[PatchOp] = []
    for idx, raw in enumerate(ops_any):
        if not _is_str_object_dict(raw):
            return _patch_validation_error(
                index=idx,
                path=f"$.ops[{idx}]",
                reason="invalid_op",
                message="patch op must be an object",
                meta={"expected": "object"},
            )
        op_any = raw.get("op")
        path_any = raw.get("path")
        if op_any != "set":
            return _patch_validation_error(
                index=idx,
                path=f"$.ops[{idx}].op",
                reason="unknown_op",
                message="unsupported patch op",
                meta={"op": op_any},
            )
        if not isinstance(path_any, str) or not path_any.strip():
            return _patch_validation_error(
                index=idx,
                path=f"$.ops[{idx}].path",
                reason="invalid_path",
                message="patch path must be a non-empty string",
                meta={"path": path_any},
            )
        path = path_any.strip()
        if "[" in path or "]" in path:
            return _patch_validation_error(
                index=idx,
                path=f"$.ops[{idx}].path",
                reason="indexing_forbidden",
                message="list indexing is not supported in patch paths",
                meta={"path": path},
            )
        value = raw.get("value")

        err = _validate_set_path_and_value(index=idx, path=path, value=value)
        if err is not None:
            return err
        ops.append(PatchOp(op="set", path=path, value=value))

    # Read -> apply -> validate -> normalize -> atomic write -> return.
    ensure_default_models(engine._fs)
    current = read_json(engine._fs, RootName.WIZARDS, "import/config/flow_config.json")
    base = engine._normalize_flow_config(current)
    patched = apply_ops(base, ops)

    validated = engine.validate_flow_config(patched)
    if validated.get("ok") is not True:
        return validated

    normalized = engine._normalize_flow_config(patched)
    atomic_write_json(
        engine._fs,
        RootName.WIZARDS,
        "import/config/flow_config.json",
        normalized,
    )
    return normalized


def apply_ops(base_config: dict[str, object], ops: list[PatchOp]) -> dict[str, object]:
    out: dict[str, object] = _deep_copy_dict(base_config)
    for op in ops:
        if op.op != "set":
            raise ValueError("unsupported op")
        _apply_set(out, op.path, op.value)
    return out


def _apply_set(root: dict[str, object], path: str, value: object) -> None:
    segs = [s for s in path.split(".") if s]
    if not segs:
        raise ValueError("empty path")
    cur: dict[str, object] = root
    for seg in segs[:-1]:
        nxt = cur.get(seg)
        if not _is_str_object_dict(nxt):
            nxt = {}
            cur[seg] = nxt
        cur = nxt
    cur[segs[-1]] = value


def _validate_set_path_and_value(
    *,
    index: int,
    path: str,
    value: object,
) -> dict[str, object] | None:
    if path == "conflicts.policy":
        if not isinstance(value, str) or not value.strip():
            return _patch_validation_error(
                index=index,
                path=f"$.ops[{index}].value",
                reason="type_mismatch",
                message="conflicts.policy must be a non-empty string",
                meta={"path": path, "expected": "string"},
            )
        return None

    if path == "ui.verbosity":
        if not isinstance(value, str) or not value.strip():
            return _patch_validation_error(
                index=index,
                path=f"$.ops[{index}].value",
                reason="type_mismatch",
                message="ui.verbosity must be a non-empty string",
                meta={"path": path, "expected": "string"},
            )
        return None

    if path.startswith("steps."):
        segs = [s for s in path.split(".") if s]
        if len(segs) != 3 or segs[2] != "enabled":
            return _patch_validation_error(
                index=index,
                path=f"$.ops[{index}].path",
                reason="unknown_path",
                message="unsupported patch path",
                meta={"path": path},
            )
        if not segs[1]:
            return _patch_validation_error(
                index=index,
                path=f"$.ops[{index}].path",
                reason="invalid_path",
                message="steps.<step_id>.enabled requires a non-empty step_id",
                meta={"path": path},
            )
        if not isinstance(value, bool):
            return _patch_validation_error(
                index=index,
                path=f"$.ops[{index}].value",
                reason="type_mismatch",
                message="steps.<step_id>.enabled must be bool",
                meta={"path": path, "expected": "bool"},
            )
        return None

    return _patch_validation_error(
        index=index,
        path=f"$.ops[{index}].path",
        reason="unknown_path",
        message="unsupported patch path",
        meta={"path": path},
    )


def _patch_validation_error(
    *,
    index: int | None,
    path: str,
    reason: str,
    message: str,
    meta: dict[str, object],
) -> dict[str, object]:
    meta_out = dict(meta)
    if index is not None:
        meta_out["op_index"] = int(index)
    return validation_error(
        message=message,
        path=path,
        reason=reason,
        meta=meta_out,
    )


def _deep_copy_dict(d: dict[str, object]) -> dict[str, object]:
    out: dict[str, object] = {}
    for k, v in d.items():
        if _is_str_object_dict(v):
            out[k] = _deep_copy_dict(v)
        elif _is_object_list(v):
            out[k] = [(_deep_copy_dict(x) if _is_str_object_dict(x) else x) for x in v]
        else:
            out[k] = v
    return out
