"""Baseline v1 IO primitives for import DSL runtime.

ASCII-only.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Protocol, TypeGuard, cast

from audiomason.core.config_service import ConfigService
from plugins.file_io.import_runtime import normalize_relative_path
from plugins.file_io.service.types import RootName

from ..detached_runtime import rehydrate_detached_runtime_from_bootstrap
from ..file_io_facade import file_service_from_resolver


def _is_str_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in cast(dict[object, object], value))


def _as_str_object_dict(value: object) -> dict[str, object]:
    return dict(value) if _is_str_object_dict(value) else {}


class _ListEntry(Protocol):
    rel_path: str
    is_dir: bool
    size: int | None
    mtime: float | None


class _StatLike(Protocol):
    is_dir: bool
    size: int
    mtime: float


class _RuntimeFileService(Protocol):
    def list_dir(
        self,
        root: RootName,
        rel_path: str = ".",
        *,
        recursive: bool = False,
    ) -> list[_ListEntry]: ...

    def exists(self, root: RootName, rel_path: str) -> bool: ...

    def stat(self, root: RootName, rel_path: str) -> _StatLike: ...


def _normalize_rel(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("resolver-friendly rel must be str")
    if value.startswith("/") or value.startswith("\\"):
        raise ValueError("absolute refs are forbidden")
    return normalize_relative_path(value)


def _ref_object(*, root: RootName, rel: str) -> dict[str, str]:
    return {"root": root.value, "rel": rel}


def _root_from_text(text: object) -> RootName:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("resolver-friendly root is required")
    try:
        return RootName(text.strip())
    except ValueError as exc:
        raise ValueError("resolver-friendly root is invalid") from exc


def _source_ref_from_state(state: dict[str, object] | None) -> tuple[RootName | None, str]:
    state_map = state if _is_str_object_dict(state) else {}
    source = _as_str_object_dict(state_map.get("source"))
    root_any = source.get("root")
    rel_any = source.get("relative_path")
    root: RootName | None = None
    if isinstance(root_any, str) and root_any:
        try:
            root = RootName(root_any)
        except ValueError:
            root = None
    rel = ""
    if isinstance(rel_any, str):
        rel = _normalize_rel(rel_any)
    return root, rel


def _resolve_ref(
    *,
    inputs: dict[str, object],
    state: dict[str, object] | None,
) -> tuple[RootName, str]:
    state_root, state_rel = _source_ref_from_state(state)
    ref_any = inputs.get("ref")

    if _is_str_object_dict(ref_any):
        ref = _as_str_object_dict(ref_any)
        ref_root = _root_from_text(ref.get("root"))
        rel = _normalize_rel(ref.get("rel", ""))
        return ref_root, rel

    if isinstance(ref_any, str) and ref_any:
        head, sep, tail = ref_any.partition(":")
        if sep:
            ref_root = _root_from_text(head)
            rel = _normalize_rel(tail)
            return ref_root, rel
        if state_root is None:
            raise ValueError("resolver-friendly ref root is required")
        rel = _normalize_rel(ref_any)
        return state_root, rel

    root_any = inputs.get("root")
    rel_any = inputs.get("rel", inputs.get("relative_path", state_rel))
    resolved_root: RootName | None = (
        _root_from_text(root_any) if root_any is not None else state_root
    )
    if resolved_root is None:
        raise ValueError("resolver-friendly root is required")
    rel = _normalize_rel(rel_any if rel_any is not None else "")
    return resolved_root, rel


def _runtime_file_service(state: dict[str, object] | None) -> _RuntimeFileService:
    vars_map = _as_str_object_dict(_as_str_object_dict(state).get("vars"))
    runtime = _as_str_object_dict(vars_map.get("runtime"))
    bootstrap = _as_str_object_dict(runtime.get("detached_runtime"))
    if bootstrap:
        detached = rehydrate_detached_runtime_from_bootstrap(bootstrap=bootstrap)
        if detached is not None:
            return cast(_RuntimeFileService, detached.get_file_service())
    return cast(_RuntimeFileService, file_service_from_resolver(ConfigService()))


def _list_item(
    *,
    root: RootName,
    rel: str,
    is_dir: bool,
    size: object,
    mtime: object,
) -> dict[str, object]:
    return {
        "ref": _ref_object(root=root, rel=rel),
        "name": PurePosixPath(rel).name,
        "kind": "dir" if is_dir else "file",
        "size": size if isinstance(size, int) else None,
        "mtime": mtime if isinstance(mtime, (int, float)) else None,
    }


def _entry_sort_key(entry: _ListEntry) -> str:
    return entry.rel_path


def _list_operation(
    *,
    root: RootName,
    rel: str,
    recursive: bool,
    state: dict[str, object] | None,
) -> dict[str, object]:
    fs = _runtime_file_service(state)
    base_rel = rel or "."
    entries: list[_ListEntry] = fs.list_dir(root, base_rel, recursive=recursive)
    items: list[dict[str, object]] = []
    for entry in sorted(entries, key=_entry_sort_key):
        entry_rel = normalize_relative_path(str(entry.rel_path))
        items.append(
            _list_item(
                root=root,
                rel=entry_rel,
                is_dir=bool(entry.is_dir),
                size=entry.size,
                mtime=entry.mtime,
            )
        )
    return {
        "ref": _ref_object(root=root, rel=rel),
        "items": items,
    }


def _stat_operation(
    *,
    root: RootName,
    rel: str,
    state: dict[str, object] | None,
) -> dict[str, object]:
    fs = _runtime_file_service(state)
    exists = bool(fs.exists(root, rel))
    if not exists:
        return {
            "ref": _ref_object(root=root, rel=rel),
            "exists": False,
            "kind": "missing",
            "size": None,
            "mtime": None,
        }
    stat = fs.stat(root, rel)
    return {
        "ref": _ref_object(root=root, rel=rel),
        "exists": True,
        "kind": "dir" if bool(stat.is_dir) else "file",
        "size": int(stat.size),
        "mtime": float(stat.mtime),
    }


def _read_meta_operation(
    *,
    root: RootName,
    rel: str,
    state: dict[str, object] | None,
) -> dict[str, object]:
    stat_doc = _stat_operation(root=root, rel=rel, state=state)
    if stat_doc.get("exists") is not True:
        return {
            "ref": _ref_object(root=root, rel=rel),
            "exists": False,
            "meta": {},
        }

    rel_path = PurePosixPath(rel)
    parts = [segment for segment in rel_path.parts if segment not in {"", "."}]
    meta: dict[str, object] = {
        "name": rel_path.name,
        "stem": rel_path.stem,
        "suffix": rel_path.suffix.lower(),
        "suffixes": [suffix.lower() for suffix in rel_path.suffixes],
        "parts": parts,
        "kind": stat_doc.get("kind"),
        "size": stat_doc.get("size"),
        "mtime": stat_doc.get("mtime"),
    }
    return {
        "ref": _ref_object(root=root, rel=rel),
        "exists": True,
        "meta": meta,
    }


def _object_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {},
        "required": [],
        "description": "",
    }


REGISTRY_ENTRIES: list[dict[str, object]] = [
    {
        "primitive_id": "io.list",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": ["VALIDATION_ERROR"],
    },
    {
        "primitive_id": "io.stat",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": ["VALIDATION_ERROR"],
    },
    {
        "primitive_id": "io.read_meta",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": ["VALIDATION_ERROR"],
    },
]


def execute(
    primitive_id: str,
    primitive_version: int,
    inputs: dict[str, object],
    state: dict[str, object] | None = None,
) -> dict[str, object]:
    if primitive_version != 1:
        raise ValueError("unsupported primitive version")
    root, rel = _resolve_ref(inputs=inputs, state=state)
    if primitive_id == "io.list":
        recursive = bool(inputs.get("recursive", False))
        return _list_operation(root=root, rel=rel, recursive=recursive, state=state)
    if primitive_id == "io.stat":
        return _stat_operation(root=root, rel=rel, state=state)
    if primitive_id == "io.read_meta":
        return _read_meta_operation(root=root, rel=rel, state=state)
    raise ValueError("unknown io primitive")
