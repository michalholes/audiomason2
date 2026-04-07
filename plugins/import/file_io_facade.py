"""File-IO facade for the import plugin.

This module centralizes imports from plugins.file_io so that other modules in
plugins.import do not directly depend on multiple external areas.

ASCII-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from plugins.file_io.import_runtime import normalize_relative_path
from plugins.file_io.service import FileService
from plugins.file_io.service.types import RootName

from .file_io_boundary import join_source_relative_path, materialize_local_path


def file_service_from_resolver(resolver):
    return FileService.from_resolver(resolver)


ROOT_MAP = {rn.value: rn for rn in RootName}


def candidate_path_preview(
    *,
    source_relative_path: str,
    candidate_relative_path: str,
    audio_relative_path: str,
    kind: str,
) -> str:
    if kind == "embedded":
        return normalize_relative_path(audio_relative_path)
    if candidate_relative_path:
        return normalize_relative_path(candidate_relative_path)
    return normalize_relative_path(source_relative_path)


def first_audio_source(directory: Path) -> Path | None:
    embedded_suffixes = {".mp3", ".m4a", ".m4b"}
    if not directory.exists() or not directory.is_dir():
        return None
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in embedded_suffixes:
            return path
    return None


def path_to_source_relative(*, source_dir: Path, abs_path: Path) -> str:
    return abs_path.resolve().relative_to(source_dir.resolve()).as_posix()


def canonicalize_ref_candidate(
    *,
    candidate: dict[str, Any],
    source_root: RootName,
    source_relative_path: str,
) -> dict[str, str]:
    kind = str(candidate.get("kind") or "")
    entry = {
        "source_root": source_root.value,
        "source_relative_path": source_relative_path,
        "root_name": str(candidate.get("root_name") or source_root.value),
        "kind": kind,
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "apply_mode": str(candidate.get("apply_mode") or ""),
        "mime_type": str(candidate.get("mime_type") or ""),
        "cache_key": str(candidate.get("cache_key") or ""),
    }
    candidate_rel = normalize_relative_path(str(candidate.get("candidate_relative_path") or ""))
    audio_rel = normalize_relative_path(str(candidate.get("audio_relative_path") or ""))
    if candidate_rel:
        entry["candidate_relative_path"] = candidate_rel
    if audio_rel:
        entry["audio_relative_path"] = audio_rel
    url = str(candidate.get("url") or "").strip()
    if url:
        entry["url"] = url
    preview = candidate_path_preview(
        source_relative_path=source_relative_path,
        candidate_relative_path=candidate_rel,
        audio_relative_path=audio_rel,
        kind=kind,
    )
    if preview:
        entry["path"] = preview
    return entry


def canonicalize_path_candidate(
    *,
    candidate: dict[str, Any],
    source_root: RootName,
    source_dir: Path,
    source_relative_path: str,
) -> dict[str, str]:
    kind = str(candidate.get("kind") or "")
    entry = {
        "source_root": source_root.value,
        "source_relative_path": source_relative_path,
        "root_name": str(candidate.get("root_name") or source_root.value),
        "kind": kind,
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "apply_mode": str(candidate.get("apply_mode") or ""),
        "mime_type": str(candidate.get("mime_type") or ""),
        "cache_key": str(candidate.get("cache_key") or ""),
    }
    path_text = str(candidate.get("path") or "").strip()
    if path_text:
        rel = path_to_source_relative(source_dir=source_dir, abs_path=Path(path_text))
        full_rel = rel
        if source_relative_path and rel and rel != source_relative_path:
            prefix = normalize_relative_path(source_relative_path)
            if prefix and not rel.startswith(prefix + "/"):
                full_rel = join_source_relative_path(
                    source_prefix=prefix,
                    source_relative_path=rel,
                )
        if kind == "embedded":
            entry["audio_relative_path"] = full_rel
        else:
            entry["candidate_relative_path"] = full_rel
        entry["path"] = full_rel
    url = str(candidate.get("url") or "").strip()
    if url:
        entry["url"] = url
    return entry


def discover_path_cover_candidates(
    *,
    fs: FileService,
    source_root: RootName,
    source_rel: str,
    source_relative_path: str,
    group_root: str | None,
    plugin: Any,
) -> list[dict[str, str]]:
    source_dir = materialize_local_path(fs, source_root, source_rel)
    if source_dir.exists() and source_dir.is_file():
        source_dir = source_dir.parent
    if not source_dir.exists() or not source_dir.is_dir():
        return []
    candidates = plugin.discover_cover_candidates(
        source_dir,
        audio_file=first_audio_source(source_dir),
        group_root=group_root,
    )
    return [
        canonicalize_path_candidate(
            candidate=dict(candidate),
            source_root=source_root,
            source_dir=source_dir,
            source_relative_path=source_relative_path,
        )
        for candidate in candidates
        if isinstance(candidate, dict)
    ]


async def apply_path_cover_candidate(
    *,
    fs: FileService,
    candidate: dict[str, Any],
    output_root: RootName,
    output_rel: str,
    plugin: Any,
) -> dict[str, str] | None:
    mode = str(candidate.get("apply_mode") or "")
    source_root_text = str(candidate.get("source_root") or "")
    source_root = RootName(source_root_text) if source_root_text else None
    output_dir = materialize_local_path(fs, output_root, output_rel)
    output_dir.mkdir(parents=True, exist_ok=True)
    materialized: Path | None = None
    if mode == "copy" and source_root is not None:
        rel = normalize_relative_path(str(candidate.get("candidate_relative_path") or ""))
        if not rel:
            return None
        source_path = materialize_local_path(fs, source_root, rel)
        materialized = await plugin.apply_cover_candidate(
            {**dict(candidate), "path": str(source_path)},
            output_dir=output_dir,
        )
    elif mode == "extract_embedded" and source_root is not None:
        rel = normalize_relative_path(str(candidate.get("audio_relative_path") or ""))
        if not rel:
            return None
        audio_file = materialize_local_path(fs, source_root, rel)
        materialized = await plugin.extract_embedded_cover(audio_file)
    elif mode == "download":
        materialized = await plugin.download_cover(
            str(candidate.get("url") or "").strip(),
            output_dir=output_dir,
            mime_type=str(candidate.get("mime_type") or ""),
            cache_key=str(candidate.get("cache_key") or ""),
        )
    else:
        raise RuntimeError(f"Unsupported apply_mode: {mode}")

    if materialized is None:
        return None
    return {
        "root": output_root.value,
        "relative_path": join_source_relative_path(
            source_prefix=output_rel,
            source_relative_path=Path(materialized).name,
        ),
    }


__all__ = [
    "ROOT_MAP",
    "apply_path_cover_candidate",
    "candidate_path_preview",
    "canonicalize_path_candidate",
    "canonicalize_ref_candidate",
    "discover_path_cover_candidates",
    "file_service_from_resolver",
    "first_audio_source",
    "path_to_source_relative",
]
