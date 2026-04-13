"""Import-owned cover boundary adapter.

Provides registry-mediated cover callable authority for import PHASE 1/2.

ASCII-only.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol, cast

from audiomason.core.config_service import ConfigService
from audiomason.core.errors import PluginError, PluginNotFoundError
from audiomason.core.loader import PluginLoader
from audiomason.core.plugin_callable_authority import (
    RegisteredWizardCallable,
    resolve_registered_wizard_callable,
)
from audiomason.core.plugin_registry import PluginRegistry

from .file_io_boundary import (
    join_source_relative_path,
    materialize_local_path,
    normalize_root_name,
)
from .file_io_facade import (
    canonicalize_path_candidate,
    canonicalize_ref_candidate,
    first_audio_source,
)


class _DiscoverCoverCallable(Protocol):
    def __call__(
        self,
        *,
        file_service: Any,
        source_root: str,
        source_relative_path: str,
        group_root: str | None = None,
        stage_root: str | None = None,
    ) -> list[dict[str, str]]: ...


class _ApplyCoverCallable(Protocol):
    async def __call__(
        self,
        *,
        file_service: Any,
        candidate: dict[str, Any],
        output_root: str,
        output_relative_dir: str,
    ) -> dict[str, str] | None: ...


def _builtin_plugins_dir() -> Path:
    plugins_pkg = import_module("plugins")
    pkg_file = getattr(plugins_pkg, "__file__", None)
    if not isinstance(pkg_file, str) or not pkg_file:
        raise RuntimeError("plugins package path unavailable")
    return Path(pkg_file).resolve().parent


@lru_cache(maxsize=1)
def _callable_authority() -> tuple[PluginRegistry, PluginLoader]:
    registry = PluginRegistry(ConfigService())
    loader = PluginLoader(
        builtin_plugins_dir=_builtin_plugins_dir(),
        registry=registry,
    )
    return registry, loader


_LEGACY_METHOD_ALIASES = {
    "cover.discover_candidates_for_ref": ("discover_cover_candidates",),
    "cover.apply_candidate_for_ref": ("apply_cover_candidate",),
}


def _legacy_cover_callable(
    *,
    plugin_obj: object,
    callable_def: RegisteredWizardCallable,
) -> object | None:
    for method_name in _LEGACY_METHOD_ALIASES.get(callable_def.operation_id, ()):
        method = getattr(plugin_obj, method_name, None)
        if not callable(method):
            continue
        if callable_def.operation_id == "cover.discover_candidates_for_ref":
            discover_method = method

            def _discover_for_ref(
                *,
                file_service: Any,
                source_root: str,
                source_relative_path: str,
                group_root: str | None = None,
                stage_root: str | None = None,
                _discover_method: Any = discover_method,
            ) -> list[dict[str, str]]:
                del stage_root
                root_name = normalize_root_name(source_root)
                source_dir = materialize_local_path(
                    file_service,
                    root_name,
                    source_relative_path,
                )
                if source_dir.exists() and source_dir.is_file():
                    source_dir = source_dir.parent
                if not source_dir.exists() or not source_dir.is_dir():
                    return []
                kwargs: dict[str, Any] = {"audio_file": first_audio_source(source_dir)}
                if group_root is not None:
                    kwargs["group_root"] = group_root
                try:
                    candidates = _discover_method(source_dir, **kwargs)
                except TypeError:
                    kwargs.pop("group_root", None)
                    candidates = _discover_method(source_dir, **kwargs)
                return [
                    canonicalize_path_candidate(
                        candidate=dict(candidate),
                        source_root=root_name,
                        source_dir=source_dir,
                        source_relative_path=source_relative_path,
                    )
                    for candidate in candidates
                    if isinstance(candidate, dict)
                ]

            return _discover_for_ref
        if callable_def.operation_id == "cover.apply_candidate_for_ref":
            apply_method = method

            async def _apply_for_ref(
                *,
                file_service: Any,
                candidate: dict[str, Any],
                output_root: str,
                output_relative_dir: str,
                _apply_method: Any = apply_method,
            ) -> dict[str, str] | None:
                output_root_name = normalize_root_name(output_root)
                output_dir = materialize_local_path(
                    file_service,
                    output_root_name,
                    output_relative_dir,
                )
                output_dir.mkdir(parents=True, exist_ok=True)
                mode = str(candidate.get("apply_mode") or "")
                materialized: Path | None = None
                if mode == "copy":
                    source_root_text = str(candidate.get("source_root") or "")
                    candidate_rel = str(candidate.get("candidate_relative_path") or "")
                    if not source_root_text or not candidate_rel:
                        return None
                    source_path = materialize_local_path(
                        file_service,
                        normalize_root_name(source_root_text),
                        candidate_rel,
                    )
                    materialized = await _apply_method(
                        {**dict(candidate), "path": str(source_path)},
                        output_dir=output_dir,
                    )
                else:
                    raise RuntimeError(f"Unsupported apply_mode: {mode}")
                if materialized is None:
                    return None
                return {
                    "root": output_root_name.value,
                    "relative_path": join_source_relative_path(
                        source_prefix=output_relative_dir,
                        source_relative_path=Path(materialized).name,
                    ),
                }

            return _apply_for_ref
    return None


def _bind_explicit_plugin_callable(
    *,
    plugin_obj: object,
    callable_def: RegisteredWizardCallable,
) -> object:
    try:
        return resolve_registered_wizard_callable(
            plugin_obj=plugin_obj,
            callable_def=callable_def,
        )
    except PluginError:
        legacy = _legacy_cover_callable(
            plugin_obj=plugin_obj,
            callable_def=callable_def,
        )
        if legacy is not None:
            return legacy
    return resolve_registered_wizard_callable(
        plugin_obj=plugin_obj,
        callable_def=callable_def,
    )


def _published_wizard_callable(
    *,
    operation_id: str,
    expected_execution_mode: str,
    plugin_obj: object | None = None,
) -> object:
    registry, loader = _callable_authority()
    published = registry.resolve_wizard_callable(operation_id, loader=loader)
    if published.execution_mode != expected_execution_mode:
        raise RuntimeError(
            f"wizard_callable_execution_mode_mismatch:{operation_id}:{published.execution_mode}"
        )
    if plugin_obj is None:
        try:
            plugin_obj = loader.get_plugin(published.plugin_id)
        except PluginNotFoundError:
            plugin_obj = loader.load_plugin(published.manifest_path.parent, validate=False)
    callable_def = RegisteredWizardCallable(
        plugin_id=published.plugin_id,
        plugin_dir=published.manifest_path.parent,
        manifest_path=published.manifest_path,
        operation_id=published.operation_id,
        method_name=published.method_name,
        execution_mode=published.execution_mode,
    )
    return _bind_explicit_plugin_callable(
        plugin_obj=plugin_obj,
        callable_def=callable_def,
    )


def discover_cover_candidates(
    *,
    fs: Any,
    source_root: Any,
    source_prefix: str,
    source_relative_path: str,
    group_root: str | None = None,
    plugin: object | None = None,
) -> list[dict[str, str]]:
    discover_for_ref = cast(
        _DiscoverCoverCallable,
        _published_wizard_callable(
            operation_id="cover.discover_candidates_for_ref",
            expected_execution_mode="inline",
            plugin_obj=plugin,
        ),
    )
    root_name = normalize_root_name(source_root)
    source_rel = join_source_relative_path(
        source_prefix=source_prefix,
        source_relative_path=source_relative_path,
    )
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


async def apply_cover_candidate(
    *,
    fs: Any,
    candidate: dict[str, Any],
    output_root: Any,
    output_relative_dir: str,
    plugin: object | None = None,
) -> dict[str, str] | None:
    apply_for_ref = cast(
        _ApplyCoverCallable,
        _published_wizard_callable(
            operation_id="cover.apply_candidate_for_ref",
            expected_execution_mode="job",
            plugin_obj=plugin,
        ),
    )
    output_root_name = normalize_root_name(output_root)
    output_rel = join_source_relative_path(
        source_prefix="",
        source_relative_path=output_relative_dir,
    )
    return await apply_for_ref(
        file_service=fs,
        candidate=dict(candidate),
        output_root=output_root_name.value,
        output_relative_dir=output_rel,
    )


__all__ = ["apply_cover_candidate", "discover_cover_candidates"]
