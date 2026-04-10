"""Import-owned cover boundary adapter.

Provides a stable, resolver-friendly seam for import PHASE 1/2 while the
provider surface migrates from path-based to ref-based contracts.

ASCII-only.
"""

from __future__ import annotations

from typing import Any

from .engine_diagnostics_required import resolve_import_plugin
from .file_io_boundary import join_source_relative_path, normalize_root_name
from .file_io_facade import (
    apply_path_cover_candidate,
    canonicalize_ref_candidate,
    discover_path_cover_candidates,
)


def _cover_plugin(plugin: Any | None) -> Any:
    if plugin is not None:
        return plugin
    return resolve_import_plugin(plugin_name="cover_handler")


def discover_cover_candidates(
    *,
    fs: Any,
    source_root: Any,
    source_prefix: str,
    source_relative_path: str,
    group_root: str | None = None,
    plugin: Any | None = None,
) -> list[dict[str, str]]:
    plugin_obj = _cover_plugin(plugin)
    root_name = normalize_root_name(source_root)
    source_rel = join_source_relative_path(
        source_prefix=source_prefix,
        source_relative_path=source_relative_path,
    )
    discover_for_ref = getattr(plugin_obj, "discover_cover_candidates_for_ref", None)
    if callable(discover_for_ref):
        candidates = discover_for_ref(
            file_service=fs,
            source_root=root_name.value,
            source_relative_path=source_rel,
            group_root=group_root,
        )
        return [
            canonicalize_ref_candidate(
                candidate=dict(candidate),
                source_root=root_name,
                source_relative_path=source_relative_path,
            )
            for candidate in candidates
            if isinstance(candidate, dict)
        ]
    return discover_path_cover_candidates(
        fs=fs,
        source_root=root_name,
        source_rel=source_rel,
        source_relative_path=source_relative_path,
        group_root=group_root,
        plugin=plugin_obj,
    )


async def apply_cover_candidate(
    *,
    fs: Any,
    candidate: dict[str, Any],
    output_root: Any,
    output_relative_dir: str,
    plugin: Any | None = None,
) -> dict[str, str] | None:
    plugin_obj = _cover_plugin(plugin)
    output_root_name = normalize_root_name(output_root)
    output_rel = join_source_relative_path(
        source_prefix="",
        source_relative_path=output_relative_dir,
    )
    apply_for_ref = getattr(plugin_obj, "apply_cover_candidate_for_ref", None)
    if callable(apply_for_ref):
        return await apply_for_ref(
            file_service=fs,
            candidate=dict(candidate),
            output_root=output_root_name.value,
            output_relative_dir=output_rel,
        )
    return await apply_path_cover_candidate(
        fs=fs,
        candidate=candidate,
        output_root=output_root_name,
        output_rel=output_rel,
        plugin=plugin_obj,
    )


__all__ = ["apply_cover_candidate", "discover_cover_candidates"]
