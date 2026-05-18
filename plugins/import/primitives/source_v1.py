"""Baseline v1 source primitives for import DSL runtime.

ASCII-only.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from ..detached_runtime import rehydrate_detached_runtime_from_bootstrap
from ..discovery import run_discovery
from ..fingerprints import sha256_hex

_TRAILING_TAG_RE = re.compile(r"(?:\s*(?:\([^)]*\)|\[[^]]*\]))+\s*$")


def _ascii_fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return normalized.encode("ascii", "ignore").decode("ascii")


def _cleanup_whitespace(text: str) -> str:
    return " ".join(part for part in str(text).replace("_", " ").split() if part)


def _strip_trailing_tags(text: str) -> str:
    previous = str(text)
    while True:
        updated = _TRAILING_TAG_RE.sub("", previous).strip()
        if updated == previous:
            return updated
        previous = updated


def _normalize_label(value: Any) -> str:
    text = _cleanup_whitespace(str(value or ""))
    text = _strip_trailing_tags(text)
    if "," in text:
        parts = [part.strip() for part in text.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            text = f"{parts[1]} {parts[0]}"
    text = _cleanup_whitespace(_ascii_fold(text))
    return text


def _normalize_rel_path(value: str) -> str:
    rel = value.replace("\\", "/").strip("/")
    return "/".join(part for part in rel.split("/") if part)


def _strip_source_prefix(*, rel_path: str, source_prefix: str) -> str:
    if not source_prefix:
        return rel_path
    if rel_path == source_prefix:
        return ""
    prefix = source_prefix + "/"
    if rel_path.startswith(prefix):
        return rel_path[len(prefix):]
    return rel_path


def _scope_tail(scope_path: str) -> str:
    parts = [part for part in scope_path.split("/") if part]
    return parts[-1] if parts else "(root)"


def _scope_parent_tail(scope_path: str) -> str:
    parts = [part for part in scope_path.split("/") if part]
    return parts[-2] if len(parts) >= 2 else _scope_tail(scope_path)


def _scoped_depth(*, rel_path: str, is_file: bool) -> int:
    parts = [part for part in rel_path.split("/") if part]
    if is_file and parts:
        return len(parts[:-1])
    return len(parts)


def _scope_kind(*, source_prefix: str, dirs: list[str], files: list[str]) -> str:
    if not source_prefix:
        return "root"
    depths = [_scoped_depth(rel_path=rel, is_file=False) for rel in dirs if rel]
    depths.extend(_scoped_depth(rel_path=rel, is_file=True) for rel in files if rel)
    max_depth = max(depths, default=0)
    if max_depth >= 2:
        return "container"
    if max_depth == 1:
        return "author"
    if len([part for part in source_prefix.split("/") if part]) >= 2:
        return "book"
    return "container"


def _collect_scoped_entries(
    *,
    discovery: list[dict[str, Any]],
    source_prefix: str,
) -> tuple[list[str], list[str]]:
    dirs: list[str] = []
    files: list[str] = []
    for item in discovery:
        if not isinstance(item, dict):
            continue
        rel_any = item.get("relative_path")
        if not isinstance(rel_any, str):
            continue
        rel = _strip_source_prefix(
            rel_path=_normalize_rel_path(rel_any),
            source_prefix=source_prefix,
        )
        kind = str(item.get("kind") or "")
        if kind == "dir":
            dirs.append(rel)
        elif kind in {"file", "bundle"}:
            files.append(rel)
    return dirs, files


def _pairs_for_multilevel_scope(
    *,
    dirs: list[str],
    files: list[str],
) -> set[tuple[str, str, str]]:
    pairs: set[tuple[str, str, str]] = set()
    for rel in dirs:
        parts = [part for part in rel.split("/") if part]
        if len(parts) >= 2:
            pairs.add((parts[0], parts[1], f"{parts[0]}/{parts[1]}"))
    if not pairs:
        for rel in dirs:
            parts = [part for part in rel.split("/") if part]
            if parts:
                pairs.add((parts[0], parts[0], parts[0]))
    if not pairs:
        for rel in files:
            parts = [part for part in rel.split("/") if part]
            parent_parts = parts[:-1]
            if len(parent_parts) >= 2:
                pairs.add(
                    (
                        parent_parts[0],
                        parent_parts[1],
                        f"{parent_parts[0]}/{parent_parts[1]}",
                    )
                )
            elif len(parent_parts) == 1:
                pairs.add((parent_parts[0], parent_parts[0], parent_parts[0]))
            elif parts:
                pairs.add(("(root)", "(root)", ""))
    return pairs


def _pairs_for_author_scope(
    *,
    source_prefix: str,
    dirs: list[str],
    files: list[str],
) -> set[tuple[str, str, str]]:
    author_key = _scope_tail(source_prefix)
    pairs: set[tuple[str, str, str]] = set()
    for rel in dirs:
        parts = [part for part in rel.split("/") if part]
        if parts:
            pairs.add((author_key, parts[0], parts[0]))
    if not pairs:
        for rel in files:
            parent_parts = [part for part in rel.split("/") if part][:-1]
            if parent_parts:
                pairs.add((author_key, parent_parts[0], parent_parts[0]))
    if not pairs:
        pairs.add((author_key, author_key, ""))
    return pairs


def _pairs_for_book_scope(source_prefix: str) -> set[tuple[str, str, str]]:
    author_key = _scope_parent_tail(source_prefix)
    book_key = _scope_tail(source_prefix)
    return {(author_key, book_key, "")}


def _discovery_pairs(
    *,
    discovery: list[dict[str, Any]],
    source_prefix: str,
) -> list[tuple[str, str, str]]:
    dirs, files = _collect_scoped_entries(discovery=discovery, source_prefix=source_prefix)
    scope = _scope_kind(source_prefix=source_prefix, dirs=dirs, files=files)
    if scope in {"root", "container"}:
        pairs = _pairs_for_multilevel_scope(dirs=dirs, files=files)
    elif scope == "author":
        pairs = _pairs_for_author_scope(
            source_prefix=source_prefix,
            dirs=dirs,
            files=files,
        )
    else:
        pairs = _pairs_for_book_scope(source_prefix)
    return sorted(pairs)


def _build_catalog(
    *,
    discovery: list[dict[str, Any]],
    source_prefix: str,
) -> dict[str, Any]:
    pairs = _discovery_pairs(discovery=discovery, source_prefix=source_prefix)

    authors: dict[str, dict[str, str]] = {}
    books: dict[str, dict[str, str]] = {}
    author_to_books: dict[str, list[str]] = {}

    for author_key, book_key, source_relative_path in pairs:
        author_id = "author:" + sha256_hex(f"a|{author_key}".encode())[:16]
        book_id = "book:" + sha256_hex(f"b|{author_key}|{book_key}".encode())[:16]
        authors.setdefault(author_id, {"label": author_key})
        books.setdefault(
            book_id,
            {
                "label": book_key if author_key == book_key else f"{author_key} / {book_key}",
                "author_id": author_id,
                "source_relative_path": source_relative_path,
            },
        )
        author_to_books.setdefault(author_id, []).append(book_id)

    author_items = sorted(authors.items(), key=lambda kv: (kv[1]["label"], kv[0]))
    book_items = sorted(books.items(), key=lambda kv: (kv[1]["label"], kv[0]))
    ordered_author_ids = [k for k, _ in author_items]
    ordered_book_ids = [k for k, _ in book_items]

    for author_id in author_to_books:
        seen: set[str] = set()
        ordered: list[str] = []
        for book_id in ordered_book_ids:
            if book_id in author_to_books[author_id] and book_id not in seen:
                ordered.append(book_id)
                seen.add(book_id)
        author_to_books[author_id] = ordered

    return {
        "authors": authors,
        "books": books,
        "author_to_books": author_to_books,
        "ordered_author_ids": ordered_author_ids,
        "ordered_book_ids": ordered_book_ids,
    }


def execute(
    primitive_id: str,
    primitive_version: int,
    inputs: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    if primitive_id == "source.build_catalog":
        root = str(inputs.get("root") or "")
        relative_path = str(inputs.get("relative_path") or "")
        vars_any = state.get("vars")
        vars_map = dict(vars_any) if isinstance(vars_any, dict) else {}
        runtime_any = vars_map.get("runtime")
        runtime = dict(runtime_any) if isinstance(runtime_any, dict) else {}
        bootstrap_any = runtime.get("detached_runtime")
        bootstrap = dict(bootstrap_any) if isinstance(bootstrap_any, dict) else {}
        if not bootstrap:
            raise ValueError("source.build_catalog requires vars.runtime.detached_runtime in state")
        detached = rehydrate_detached_runtime_from_bootstrap(bootstrap=bootstrap)
        if detached is None:
            raise ValueError("source.build_catalog: failed to rehydrate detached runtime")
        fs_any = detached.get_file_service()
        discovery = run_discovery(fs_any, root=root, relative_path=relative_path)
        source_prefix_raw = relative_path.replace("\\", "/").strip("/")
        source_prefix = "/".join(part for part in source_prefix_raw.split("/") if part)
        return _build_catalog(discovery=discovery, source_prefix=source_prefix)

    if primitive_id == "source.normalize_label":
        value = inputs.get("value")
        return {"normalized": _normalize_label(value)}

    if primitive_id == "source.keys":
        items_any = inputs.get("items")
        items = dict(items_any) if isinstance(items_any, dict) else {}
        return {"keys": list(items.keys())}

    raise ValueError(f"unknown primitive: {primitive_id}")


def _object_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {},
        "required": [],
        "description": "",
    }


REGISTRY_ENTRIES: list[dict[str, Any]] = [
    {
        "primitive_id": "source.build_catalog",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic given same filesystem state",
        "allowed_errors": [],
    },
    {
        "primitive_id": "source.normalize_label",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": [],
    },
    {
        "primitive_id": "source.keys",
        "version": 1,
        "phase": 1,
        "inputs_schema": _object_schema(),
        "outputs_schema": _object_schema(),
        "determinism_notes": "deterministic",
        "allowed_errors": [],
    },
]

__all__ = ["REGISTRY_ENTRIES", "execute"]
