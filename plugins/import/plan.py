"""Plan computation for import wizard engine.

This is a minimal baseline planner.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from .fingerprints import sha256_hex


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
        return rel_path[len(prefix) :]
    return rel_path


class PlanSelectionError(ValueError):
    """Raised when a plan cannot be computed due to invalid selection."""


def _to_ascii(text: str) -> str:
    return text.encode("ascii", errors="replace").decode("ascii")


def _derive_book_units(
    discovery: list[dict[str, Any]],
    *,
    source_relative_path: str,
) -> dict[str, dict[str, str]]:
    """Return mapping: book_id -> unit data derived from source-scoped discovery."""

    source_prefix = _normalize_rel_path(source_relative_path)
    dirs: list[str] = []
    for it in discovery:
        if not (isinstance(it, dict) and it.get("kind") == "dir"):
            continue
        rel_any = it.get("relative_path")
        if isinstance(rel_any, str):
            rel = _strip_source_prefix(
                rel_path=_normalize_rel_path(rel_any),
                source_prefix=source_prefix,
            )
            dirs.append(rel)

    pairs: set[tuple[str, str]] = set()
    for rel in dirs:
        segs = [s for s in rel.split("/") if s]
        if len(segs) >= 2:
            pairs.add((segs[0], segs[1]))

    if not pairs:
        for rel in dirs:
            segs = [s for s in rel.split("/") if s]
            if len(segs) >= 1:
                pairs.add((segs[0], segs[0]))

    if not pairs:
        pairs.add(("(root)", "(root)"))

    units: dict[str, dict[str, str]] = {}
    for author_key, book_key in sorted(pairs):
        book_id = "book:" + sha256_hex(f"b|{author_key}|{book_key}".encode())[:16]

        if author_key == "(root)":
            source_rel = ""
        elif author_key == book_key:
            source_rel = author_key
        else:
            source_rel = f"{author_key}/{book_key}"

        display_label = author_key if author_key == book_key else f"{author_key} / {book_key}"
        label = _to_ascii(display_label)

        units[book_id] = {
            "book_id": book_id,
            "label": label,
            "display_label": display_label,
            "source_relative_path": source_rel,
            "proposed_target_relative_path": source_rel,
        }

    return units


def _filter_discovery_for_books(
    discovery: list[dict[str, Any]],
    selected_units: list[dict[str, str]],
    *,
    source_relative_path: str,
) -> list[dict[str, Any]]:
    source_prefix = _normalize_rel_path(source_relative_path)
    prefixes = []
    for u in selected_units:
        p = str(u.get("source_relative_path") or "")
        if p == "":
            # Selecting the session root implies selecting everything in discovery.
            return list(discovery)
        if p and not p.endswith("/"):
            p = p + "/"
        prefixes.append(p)

    if not prefixes:
        return []

    filtered: list[dict[str, Any]] = []
    for it in discovery:
        rel_any = it.get("relative_path")
        if not isinstance(rel_any, str):
            continue
        rel = _strip_source_prefix(
            rel_path=_normalize_rel_path(rel_any),
            source_prefix=source_prefix,
        )
        if any(rel == p[:-1] or rel.startswith(p) for p in prefixes if p):
            filtered.append(it)
    return filtered


def compute_plan(
    *,
    session_id: str,
    root: str,
    relative_path: str,
    discovery: list[dict[str, Any]],
    inputs: dict[str, Any],
    selected_book_ids: list[str],
) -> dict[str, Any]:
    units_by_id = _derive_book_units(discovery, source_relative_path=relative_path)

    selected_units: list[dict[str, str]] = []
    for bid in selected_book_ids:
        if not isinstance(bid, str):
            continue
        unit = units_by_id.get(bid)
        if unit is None:
            raise PlanSelectionError("invalid selected_book_ids")
        selected_units.append(unit)

    # Canonical order: preserve selectable item ordering (label,id).
    selected_units = sorted(selected_units, key=lambda x: (x["label"], x["book_id"]))

    selected_discovery = _filter_discovery_for_books(
        discovery,
        selected_units,
        source_relative_path=relative_path,
    )
    files = sum(1 for it in selected_discovery if it.get("kind") == "file")
    dirs = sum(1 for it in selected_discovery if it.get("kind") == "dir")
    bundles = sum(1 for it in selected_discovery if it.get("kind") == "bundle")

    selected = {
        "filename_policy": inputs.get("filename_policy"),
        "covers_policy": inputs.get("covers_policy"),
        "id3_policy": inputs.get("id3_policy"),
        "audio_processing": inputs.get("audio_processing"),
        "publish_policy": inputs.get("publish_policy"),
        "delete_source_policy": inputs.get("delete_source_policy"),
        "conflict_policy": inputs.get("conflict_policy"),
        "parallelism": inputs.get("parallelism"),
    }

    return {
        "version": 1,
        "session_id": session_id,
        "source": {"root": root, "relative_path": relative_path},
        "selected_books": selected_units,
        "summary": {
            "selected_books": len(selected_units),
            "discovered_items": len(discovery),
            "files": files,
            "dirs": dirs,
            "bundles": bundles,
        },
        "selected_policies": selected,
    }
